"""Film Maker: a small window for writing and making films.

    python -m filmengine.app

Built for screen reader users. Only standard Windows controls are used,
because screen readers read those properly. Every control has a text label
just before it in the tab order, and every action is in a menu with a
keyboard shortcut. Results and problems appear in dialogs so they are read
out, and the Messages box keeps a full record.
"""

import os
import re
import sys
import threading
import traceback

import wx

from . import audio, builtin_sounds, films, voices
from .errors import FilmError, ScriptErrors
from .paths import CACHE_DIR, ROOT
from .script import CAST_LINE, Line

APP_NAME = "Film Maker"


def report_crash(details_text=None):
    CACHE_DIR.mkdir(exist_ok=True)
    details = CACHE_DIR / "last-error.txt"
    details.write_text(details_text or traceback.format_exc(), encoding="utf-8")
    return ("Something went wrong inside the engine. This is not a mistake in your script.\n\n"
            f"Please send the file {details} to the person who looks after the engine.")


def length_words(seconds):
    minutes, secs = divmod(int(round(seconds)), 60)
    parts = []
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    parts.append(f"{secs} second" + ("s" if secs != 1 else ""))
    return " ".join(parts)


# ------------------------------------------------------------------ dialogs

class ReportDialog(wx.Dialog):
    """Shows a long message in a read-only text box, so it can be read line by line."""

    def __init__(self, parent, title, text):
        super().__init__(parent, title=title, size=(640, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="&Details:"), 0, wx.ALL, 8)
        self.text = wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY)
        sizer.Add(self.text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        close = wx.Button(self, wx.ID_OK, "&Close")
        close.SetDefault()
        sizer.Add(close, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetEscapeId(wx.ID_OK)
        self.SetSizer(sizer)
        self.text.SetFocus()
        self.text.SetInsertionPoint(0)


class FormDialog(wx.Dialog):
    """A dialog of labelled fields with OK and Cancel."""

    def __init__(self, parent, title):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

    def field(self, label, control, grow=0):
        self.sizer.Add(wx.StaticText(self, label=label), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.sizer.Add(control, grow, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        return control

    def finish(self, extra_buttons=()):
        row = wx.BoxSizer(wx.HORIZONTAL)
        for button in extra_buttons:
            row.Add(button, 0, wx.RIGHT, 8)
        row.AddStretchSpacer()
        ok = wx.Button(self, wx.ID_OK, "&OK")
        ok.SetDefault()
        row.Add(ok, 0, wx.RIGHT, 8)
        row.Add(wx.Button(self, wx.ID_CANCEL, "Cancel"))
        self.sizer.Add(row, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(self.sizer)
        self.SetMinSize((520, -1))
        self.Fit()
        self.CentreOnParent()


def voice_choices():
    """(label read to the user, name written in the script) for each voice."""
    choices = []
    # Microsoft David and Zira first: they are what screen reader users know.
    for name in sorted(voices.sapi_voices(), key=lambda n: (not n.startswith("Microsoft"), n)):
        short = name.replace(" Desktop", "")
        choices.append((f"{short}, a Windows screen reader voice, works without internet", short))
    online = sorted((v for v in voices.all_voices() if v["locale"].startswith("en-")),
                    key=lambda v: (v["locale"], v["name"]))
    for v in online:
        short = voices.short_name(v["name"])
        try:
            written = short if voices.resolve(short) == v["name"] else v["name"]
        except FilmError:
            written = v["name"]
        choices.append((f'{short}, {v["gender"].lower()}, {v["language"].split(" - ")[-1] or v["locale"]}', written))
    return choices


SETTING = re.compile(r"^(rate|speed|pitch|volume)\s*:?\s*([+-]?\d+(?:\.\d+)?)\s*(%|hz)?$", re.IGNORECASE)


def split_settings(options):
    """'low, rate -10%, volume 80' -> (rate -10, pitch 0, volume 80, 'low')."""
    rate, pitch, volume, others = 0, 0, 100.0, []
    for piece in (p.strip() for p in options.split(",")):
        match = SETTING.match(piece)
        if not match:
            if piece:
                others.append(piece)
        elif match.group(1).lower() in ("rate", "speed"):
            rate += int(float(match.group(2)))
        elif match.group(1).lower() == "pitch":
            pitch += int(float(match.group(2)))
        else:
            volume *= float(match.group(2)) / 100
    return rate, pitch, int(round(volume)), ", ".join(others)


class VoiceSliders:
    """Speed, pitch and volume sliders. Screen readers read each slider's number as it moves:
    arrow keys move by 1, Page Up and Page Down by 10, Home and End go to the ends."""

    def __init__(self, dialog, rate=0, pitch=0, volume=100):
        self.rate = self._slider(dialog, "S&peed, in percent. 0 is normal, below 0 is slower, above 0 is faster:",
                                 rate, -50, 100)
        self.pitch = self._slider(dialog, "Pitc&h, in hertz. 0 is normal, below 0 is deeper, above 0 is higher. "
                                  "Windows voices ignore pitch:", pitch, -50, 50)
        self.volume = self._slider(dialog, "Vol&ume, in percent. 100 is normal:", volume, 0, 200)
        reset = wx.Button(dialog, label="&Reset speed, pitch and volume")
        reset.Bind(wx.EVT_BUTTON, self.on_reset)
        dialog.sizer.Add(reset, 0, wx.LEFT | wx.TOP, 8)

    @staticmethod
    def _slider(dialog, label, value, low, high):
        slider = wx.Slider(dialog, value=max(low, min(high, value)), minValue=low, maxValue=high,
                           style=wx.SL_HORIZONTAL)
        slider.SetLineSize(1)
        slider.SetPageSize(10)
        return dialog.field(label, slider)

    def on_reset(self, event):
        self.rate.SetValue(0)
        self.pitch.SetValue(0)
        self.volume.SetValue(100)

    def text(self):
        """The settings as script words, leaving out anything at its normal value."""
        parts = []
        if self.rate.GetValue():
            parts.append(f"rate {self.rate.GetValue():+d}%")
        if self.pitch.GetValue():
            parts.append(f"pitch {self.pitch.GetValue():+d}hz")
        if self.volume.GetValue() != 100:
            parts.append(f"volume {self.volume.GetValue()}")
        return ", ".join(parts)


def join_options(*parts):
    return ", ".join(p.strip().strip(",").strip() for p in parts if p and p.strip().strip(","))


class CharacterDialog(FormDialog):
    """Adds a character, or with an existing cast line, changes their voice."""

    def __init__(self, parent, choices, name="", voice=None, options=""):
        super().__init__(parent, "Change a character's voice" if voice else "Add a character")
        rate, pitch, volume, styles = split_settings(options)
        self.choices = list(choices)
        if voice and not any(c[1].lower() == voice.lower() for c in self.choices):
            self.choices.insert(0, (f"{voice}, the voice this character has now", voice))
        self.name = self.field("Character's &name:", wx.TextCtrl(self, value=name))
        self.voice = self.field("&Voice:", wx.ListBox(self, choices=[c[0] for c in self.choices],
                                                       size=(-1, 200)), 1)
        chosen = [i for i, c in enumerate(self.choices) if voice and c[1].lower() == voice.lower()]
        if self.choices:
            self.voice.SetSelection(chosen[0] if chosen else 0)
        self.sliders = VoiceSliders(self, rate, pitch, volume)
        self.styles = self.field("Other &styles, separated by commas, or leave empty. For example: low, radio",
                                 wx.TextCtrl(self, value=styles))
        self.try_button = wx.Button(self, label="&Try this voice")
        self.try_button.Bind(wx.EVT_BUTTON, self.on_try)
        self.finish([self.try_button])
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        (self.voice if voice else self.name).SetFocus()

    def voice_name(self):
        i = self.voice.GetSelection()
        return self.choices[i][1] if i != wx.NOT_FOUND else None

    def options(self):
        return join_options(self.sliders.text(), self.styles.GetValue())

    def on_try(self, event):
        voice = self.voice_name()
        if voice:
            self.GetParent().try_voice(voice, "", self.options())

    def on_ok(self, event):
        if not self.name.GetValue().strip():
            wx.MessageBox("Type the character's name first.", "Add a character", parent=self)
            self.name.SetFocus()
            return
        if any(c in self.name.GetValue() for c in ":=()[]"):
            wx.MessageBox("A character's name can't have any of these in it:  : = ( ) [ ]",
                          "Add a character", parent=self)
            self.name.SetFocus()
            return
        event.Skip()

    def line(self):
        options = self.options()
        return f"{self.name.GetValue().strip()} = {self.voice_name()}" + (f", {options}" if options else "")


class LineDialog(FormDialog):
    """A spoken line. The sliders change only this line, on top of the character's own settings."""

    def __init__(self, parent, cast):
        super().__init__(parent, "Add a spoken line")
        self.who = self.field("&Who speaks:", wx.Choice(self, choices=cast))
        self.who.SetSelection(0)
        self.words = self.field("Wo&rds they say:", wx.TextCtrl(self, size=(-1, 70), style=wx.TE_MULTILINE), 1)
        self.styles = self.field("How they sa&y it, or leave empty. For example: whisper, behind",
                                 wx.TextCtrl(self))
        self.sliders = VoiceSliders(self)
        self.finish()
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.who.SetFocus()

    def on_ok(self, event):
        if not self.words.GetValue().strip():
            wx.MessageBox("Type the words they say first.", "Add a spoken line", parent=self)
            self.words.SetFocus()
            return
        event.Skip()

    def line(self):
        styles = join_options(self.styles.GetValue(), self.sliders.text())
        words = " ".join(self.words.GetValue().split())
        return f"{self.who.GetStringSelection()}" + (f" ({styles})" if styles else "") + f": {words}"


SOUND_KINDS = [
    ("A sound effect that plays once", "sound"),
    ("Music, which repeats until it is stopped", "music"),
    ("Ambience, such as rain, which repeats until it is stopped", "ambience"),
    ("Background, a second repeating sound", "background"),
]


class SoundDialog(FormDialog):
    def __init__(self, parent, film_dir):
        super().__init__(parent, "Add a sound or music")
        from .render import SoundFinder

        self.kind = self.field("&Kind of sound:", wx.Choice(self, choices=[k[0] for k in SOUND_KINDS]))
        self.kind.SetSelection(0)
        self.sounds = []
        with wx.BusyCursor():
            index = SoundFinder(film_dir).index() if film_dir else {}
        for stem, path in sorted(index.items()):
            where = "this film's sounds" if film_dir and film_dir in path.parents else "sound library"
            self.sounds.append((f"{path.stem}, a sound file from the {where}", path.stem, path))
        for name, (_, description) in builtin_sounds.BUILTIN.items():
            if name not in index:
                self.sounds.append((f"{name}, built in: {description}", name, None))
        self.sound = self.field("&Sound:", wx.ListBox(self, choices=[s[0] for s in self.sounds], size=(-1, 220)), 1)
        self.sound.SetSelection(0)
        self.options = self.field("&Options, separated by commas, or leave empty. "
                                  "For example: nowait, left, volume 50, fade in 2", wx.TextCtrl(self))
        listen = wx.Button(self, label="&Listen")
        listen.Bind(wx.EVT_BUTTON, self.on_listen)
        self.finish([listen])
        self.kind.SetFocus()

    def on_listen(self, event):
        label, name, path = self.sounds[self.sound.GetSelection()]
        if path is None:
            path = audio.save(builtin_sounds.get(name), CACHE_DIR / "listen.wav")
        os.startfile(path)

    def line(self):
        kind = SOUND_KINDS[self.kind.GetSelection()][1]
        name = self.sounds[self.sound.GetSelection()][1]
        options = self.options.GetValue().strip().strip(",")
        return f"[{kind}: {name}" + (f", {options}" if options else "") + "]"


class StopDialog(FormDialog):
    WHAT = [("Everything that is playing", "all"), ("The music", "music"),
            ("The ambience", "ambience"), ("The background", "background")]

    def __init__(self, parent):
        super().__init__(parent, "Stop sounds")
        self.what = self.field("&What to stop:", wx.Choice(self, choices=[w[0] for w in self.WHAT]))
        self.what.SetSelection(0)
        self.fade = self.field("&Fade out over how many seconds. Leave empty to stop after 1 second:",
                               wx.TextCtrl(self, value="3"))
        self.finish()
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.what.SetFocus()

    def on_ok(self, event):
        value = self.fade.GetValue().strip()
        try:
            if value:
                float(value)
        except ValueError:
            wx.MessageBox("Type the number of seconds in digits, such as 3.", "Stop sounds", parent=self)
            self.fade.SetFocus()
            return
        event.Skip()

    def line(self):
        what = self.WHAT[self.what.GetSelection()][1]
        fade = self.fade.GetValue().strip()
        return f"[stop {what}" + (f", fade out {fade}" if fade else "") + "]"


# ------------------------------------------------------------------ main window

class FilmMaker(wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_NAME, size=(1100, 760))
        self.script_path = None
        self.dirty = False
        self.busy = False
        self.find_text = ""

        panel = wx.Panel(self)
        left = wx.BoxSizer(wx.VERTICAL)
        left.Add(wx.StaticText(panel, label="Film &list:"), 0, wx.BOTTOM, 4)
        self.film_list = wx.ListBox(panel, size=(260, -1))
        left.Add(self.film_list, 1, wx.EXPAND)
        self.buttons = {}
        for key, label, handler in [("new", "&New film", self.on_new), ("make", "Ma&ke film", self.on_make),
                                    ("check", "&Check script", self.on_check), ("play", "&Play film", self.on_play)]:
            button = wx.Button(panel, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            left.Add(button, 0, wx.EXPAND | wx.TOP, 6)
            self.buttons[key] = button

        right = wx.BoxSizer(wx.VERTICAL)
        right.Add(wx.StaticText(panel, label="&Script:"), 0, wx.BOTTOM, 4)
        self.editor = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_NOHIDESEL)
        self.editor.SetFont(wx.Font(12, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        right.Add(self.editor, 3, wx.EXPAND)
        right.Add(wx.StaticText(panel, label="Messa&ges:"), 0, wx.TOP | wx.BOTTOM, 4)
        self.messages = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 140))
        right.Add(self.messages, 1, wx.EXPAND)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(left, 0, wx.EXPAND | wx.ALL, 8)
        row.Add(right, 1, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(row)

        self.CreateStatusBar()
        self.build_menus()
        self.film_list.Bind(wx.EVT_LISTBOX, self.on_pick_film)
        self.editor.Bind(wx.EVT_TEXT, self.on_edit)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.refresh_films()
        self.Centre()

    # ---------- menus

    def build_menus(self):
        bar = wx.MenuBar()
        self.busy_items = []

        def menu(title, items):
            m = wx.Menu()
            for item in items:
                if item is None:
                    m.AppendSeparator()
                    continue
                label, help_text, handler, *flags = item
                entry = m.Append(wx.ID_ANY, label, help_text)
                self.Bind(wx.EVT_MENU, handler, entry)
                if flags:
                    self.busy_items.append(entry)
            bar.Append(m, title)

        menu("&File", [
            ("&New film...\tCtrl+N", "Start a new film", self.on_new),
            ("&Save script\tCtrl+S", "Save the script", self.on_save),
            ("&Refresh film list\tCtrl+R", "Look for new film folders", lambda e: self.refresh_films()),
            ("&Open film folder", "Open the film's folder in File Explorer", self.on_open_folder),
            None,
            ("E&xit\tAlt+F4", "Close Film Maker", lambda e: self.Close()),
        ])
        menu("&Edit", [
            ("&Find...\tCtrl+F", "Find words in the script", self.on_find),
            ("Find &next\tF3", "Find the same words again", self.on_find_next),
            ("&Go to line...\tCtrl+G", "Move to a line number", self.on_goto),
        ])
        menu("Fil&m", [
            ("&Make film\tF5", "Make the audio file for this film", self.on_make, True),
            ("&Check script\tF7", "Look for mistakes without making the film", self.on_check, True),
            ("&Play film\tF9", "Listen to the finished film", self.on_play),
            None,
            ("Open &timeline", "What happens at each minute and second", self.on_open_timeline),
            ("Open &lines list", "Every spoken line with its id, for recordings", self.on_open_lines),
        ])
        menu("&Insert", [
            ("&Character...\tCtrl+K", "Add someone to the cast and choose their voice", self.on_insert_character),
            ("Change a character's &voice...\tCtrl+Shift+K", "Change the voice, speed, pitch or volume of someone "
             "in the cast", self.on_change_voice),
            ("Spoken &line...\tCtrl+L", "Add a line someone says", self.on_insert_line),
            ("&Sound or music...\tCtrl+B", "Add a sound effect, music or ambience", self.on_insert_sound),
            ("&Pause...\tCtrl+P", "Add a few seconds where nothing new happens", self.on_insert_pause),
            ("S&top sounds...\tCtrl+T", "Stop music or background sounds", self.on_insert_stop),
            ("Sc&ene...\tCtrl+E", "Mark the start of a scene", self.on_insert_scene),
        ])
        menu("&Tools", [
            ("Try a &voice...\tCtrl+Shift+V", "Hear any voice say anything", self.on_try_voice),
            ("&Word list", "Every style, effect and option word", self.on_word_list),
        ])
        menu("&Help", [
            ("&Syntax examples\tF1", "How each kind of line should look", lambda e: self.open_doc("Syntax.txt")),
            ("Script &guide", "Everything a script can do", lambda e: self.open_doc("Script guide.txt")),
            ("&Read me first", "How to use the film engine", lambda e: self.open_doc("Read me first.txt")),
            ("&Keyboard shortcuts", "Every shortcut in Film Maker", self.on_shortcuts),
        ])
        self.SetMenuBar(bar)

    # ---------- small helpers

    def say(self, text):
        """Add to the Messages box and the status bar. Safe to call from any thread."""
        def add():
            self.messages.AppendText(text + "\n")
            self.SetStatusText(text)
        wx.CallAfter(add)

    def report(self, title, text):
        with ReportDialog(self, title, text) as dialog:
            dialog.ShowModal()

    def tell(self, text, title=APP_NAME):
        wx.MessageBox(text, title, wx.OK | wx.ICON_INFORMATION, self)

    def update_title(self):
        name = self.script_path.parent.name if self.script_path else "no film open"
        self.SetTitle(f"{name}{' (not saved)' if self.dirty else ''} - {APP_NAME}")

    def need_film(self):
        if self.script_path is None:
            self.tell("Pick a film from the film list first, or make a new one with Control N.")
            return False
        return True

    def set_busy(self, busy):
        self.busy = busy
        for key in ("make", "check"):
            self.buttons[key].Enable(not busy)
        for item in self.busy_items:
            item.Enable(not busy)

    def run_in_background(self, work, done):
        """Run work() away from the window so it stays usable, then done(result, error) on the window."""
        self.set_busy(True)

        def runner():
            try:
                result, error = work(), None
            except ScriptErrors as e:
                result, error = None, e
            except FilmError as e:
                result, error = None, e
            except Exception:
                result, error = None, RuntimeError(report_crash())
            wx.CallAfter(finish, result, error)

        def finish(result, error):
            self.set_busy(False)
            done(result, error)

        threading.Thread(target=runner, daemon=True).start()

    def show_problems(self, error, title):
        self.report(title, str(error))
        if isinstance(error, ScriptErrors):
            lines = [p.line_number for p in error.problems if p.line_number > 0]
            if lines:
                self.goto_line(lines[0])
                self.say(f"Moved to line {lines[0]}, where the first problem is.")

    def open_doc(self, name):
        os.startfile(ROOT / name)

    # ---------- films and the script

    def refresh_films(self, select=None):
        current = select or (self.script_path.parent.name if self.script_path else None)
        names = films.list_films()
        self.film_list.Set(names)
        if not names:
            self.say("There are no films yet. Press Control N to start one.")
            self.buttons["new"].SetFocus()
            self.update_title()
            return
        index = names.index(current) if current in names else 0
        self.film_list.SetSelection(index)
        if not self.script_path or self.script_path.parent.name != names[index]:
            self.load_film(names[index])
        self.film_list.SetFocus()

    def load_film(self, name):
        try:
            path = films.find_script(name)
        except FilmError as e:
            self.tell(str(e))
            return
        from .script import read_text
        self.script_path = path
        self.editor.ChangeValue(read_text(path).replace("\r\n", "\n"))
        self.editor.SetInsertionPoint(0)
        self.dirty = False
        self.update_title()
        self.say(f"Opened {name}.")

    def save(self):
        if self.script_path is None:
            return False
        text = self.editor.GetValue()
        self.script_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        self.dirty = False
        self.update_title()
        return True

    def keep_changes(self):
        """Ask about unsaved changes. False means the person chose Cancel."""
        if not self.dirty:
            return True
        answer = wx.MessageBox(f"Save the changes to {self.script_path.parent.name} first?", APP_NAME,
                               wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, self)
        if answer == wx.CANCEL:
            return False
        if answer == wx.YES:
            self.save()
        return True

    def on_pick_film(self, event):
        name = self.film_list.GetStringSelection()
        if self.script_path and name == self.script_path.parent.name:
            return
        if not self.keep_changes():
            self.film_list.SetStringSelection(self.script_path.parent.name)
            return
        self.load_film(name)

    def on_edit(self, event):
        if not self.dirty:
            self.dirty = True
            self.update_title()

    def on_close(self, event):
        if self.busy and event.CanVeto():
            if wx.MessageBox("A film is still being made. Close anyway?", APP_NAME,
                             wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                event.Veto()
                return
        if event.CanVeto() and self.script_path and not self.keep_changes():
            event.Veto()
            return
        event.Skip()

    def on_new(self, event):
        if not self.keep_changes():
            return
        with wx.TextEntryDialog(self, "Type a name for the new film, such as the haunted house:", "New film") as d:
            if d.ShowModal() != wx.ID_OK:
                return
            name = d.GetValue()
        try:
            script = films.create_film(name)
        except FilmError as e:
            self.tell(str(e), "New film")
            return
        self.script_path = None
        self.refresh_films(select=script.parent.name)
        self.editor.SetFocus()
        self.say(f"Made the new film {script.parent.name}. The starter script is in the script box.")

    def on_save(self, event):
        if self.need_film() and self.save():
            self.say("Saved.")

    def on_open_folder(self, event):
        if self.need_film():
            os.startfile(self.script_path.parent)

    # ---------- making, checking, playing

    def on_make(self, event):
        if self.busy or not self.need_film():
            return
        self.save()
        name = self.script_path.parent.name
        self.say(f"Making {name}. This can take a minute. You can keep working while you wait.")
        path = self.script_path
        self.run_in_background(lambda: films.make_film(path, say=self.say), self.made)

    def made(self, result, error):
        if error:
            self.say("The film was not made. See the problems.")
            self.show_problems(error, "The film was not made")
            return
        written, seconds = result
        self.say(f"Done. The film is {length_words(seconds)} long. Saved as {written[0].name}.")
        answer = wx.MessageBox(f"The film is ready. It is {length_words(seconds)} long.\n\n"
                               "Do you want to listen to it now?", "Film made",
                               wx.YES_NO | wx.ICON_INFORMATION, self)
        if answer == wx.YES:
            os.startfile(written[0])

    def on_check(self, event):
        if self.busy or not self.need_film():
            return
        self.save()
        self.say("Checking the script...")
        path = self.script_path
        self.run_in_background(lambda: films.check_film(path), self.checked)

    def checked(self, script, error):
        if error:
            self.say("The check found problems.")
            self.show_problems(error, "Problems in the script")
            return
        lines = sum(isinstance(e, Line) for e in script.events)
        message = f"No problems found. {len(script.cast)} characters and {lines} spoken lines."
        self.say(message)
        self.tell(message, "Check script")

    def on_play(self, event):
        if not self.need_film():
            return
        finished = films.finished_files(self.script_path.parent)
        if not finished:
            self.tell("This film hasn't been made yet. Press F5 to make it.")
            return
        os.startfile(finished[0])

    def open_made_file(self, paths, what):
        existing = [p for p in paths if p.exists()]
        if existing:
            os.startfile(max(existing, key=lambda p: p.stat().st_mtime))
        else:
            self.tell(f"There is no {what} yet. It is made with the film. Press F5 to make the film.")

    def on_open_timeline(self, event):
        if self.need_film():
            self.open_made_file(list(self.script_path.parent.glob("output/* - timeline.txt")), "timeline")

    def on_open_lines(self, event):
        if self.need_film():
            self.open_made_file([self.script_path.parent / "lines.txt"], "lines list")

    # ---------- finding

    def goto_line(self, number):
        """Move to a line number, counting from 1."""
        last = self.editor.GetNumberOfLines()
        line = max(0, min(number - 1, last - 1))
        position = self.editor.XYToPosition(0, line)
        self.editor.SetFocus()
        self.editor.SetSelection(position, position + self.editor.GetLineLength(line))
        self.editor.ShowPosition(position)

    def current_line(self):
        ok, column, line = self.editor.PositionToXY(self.editor.GetInsertionPoint())
        return (line, column) if ok else (0, 0)

    def on_goto(self, event):
        line, _ = self.current_line()
        total = self.editor.GetNumberOfLines()
        with wx.NumberEntryDialog(self, f"The script has {total} lines.", "Line number:", "Go to line",
                                  line + 1, 1, max(total, 1)) as d:
            if d.ShowModal() == wx.ID_OK:
                self.goto_line(d.GetValue())

    def on_find(self, event):
        with wx.TextEntryDialog(self, "Find what:", "Find", self.find_text) as d:
            if d.ShowModal() != wx.ID_OK or not d.GetValue():
                return
            self.find_text = d.GetValue()
        self.find_next(start_at_cursor=False)

    def on_find_next(self, event):
        if not self.find_text:
            self.on_find(event)
        else:
            self.find_next(start_at_cursor=True)

    def find_next(self, start_at_cursor):
        wanted = self.find_text.lower()
        total = self.editor.GetNumberOfLines()
        line, column = self.current_line()
        if start_at_cursor:
            _, end = self.editor.GetSelection()
            ok, column, line = self.editor.PositionToXY(end)
        for step in range(total + 1):
            index = (line + step) % total
            text = self.editor.GetLineText(index).lower()
            found = text.find(wanted, column if step == 0 else 0)
            if found >= 0:
                start = self.editor.XYToPosition(found, index)
                self.editor.SetFocus()
                self.editor.SetSelection(start, start + len(wanted))
                self.editor.ShowPosition(start)
                self.SetStatusText(f"Found on line {index + 1}.")
                return
        self.tell(f'"{self.find_text}" is not in the script.', "Find")

    # ---------- inserting

    def cast_lines(self):
        """(line index, name, voice, options) for each cast line in the script."""
        cast = []
        for i in range(self.editor.GetNumberOfLines()):
            text = self.editor.GetLineText(i).strip()
            match = CAST_LINE.match(text)
            if match and not text.startswith(("[", "#")):
                voice, _, options = match.group(2).partition(",")
                cast.append((i, match.group(1).strip(), voice.strip(), options.strip()))
        return cast

    def cast_names(self):
        return [name for _, name, _, _ in self.cast_lines()]

    def replace_line(self, index, text):
        start = self.editor.XYToPosition(0, index)
        self.editor.Replace(start, start + self.editor.GetLineLength(index), text)
        self.editor.SetInsertionPoint(start)

    def on_change_voice(self, event):
        if not self.need_film():
            return
        cast = self.cast_lines()
        if not cast:
            self.tell("There is nobody in the cast yet. Add a character first with Control K.")
            return
        line, _ = self.current_line()
        here = [i for i, c in enumerate(cast) if c[0] == line]
        with wx.SingleChoiceDialog(self, "Whose voice do you want to change?", "Change a character's voice",
                                   [f"{name}, now {voice}" + (f", {options}" if options else "")
                                    for _, name, voice, options in cast]) as d:
            d.SetSelection(here[0] if here else 0)
            if d.ShowModal() != wx.ID_OK:
                return
            index, name, voice, options = cast[d.GetSelection()]
        try:
            with wx.BusyCursor():
                choices = voice_choices()
        except FilmError as e:
            self.tell(str(e))
            return
        with CharacterDialog(self, choices, name, voice, options) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            text = dialog.line()
        self.replace_line(index, text)
        self.editor.SetFocus()
        self.say(f"Changed line {index + 1} to: {text}")

    def insert_after_line(self, line, text):
        end = self.editor.XYToPosition(0, line) + self.editor.GetLineLength(line)
        self.editor.SetInsertionPoint(end)
        self.editor.WriteText("\n" + text)

    def insert_line(self, text):
        """Add a line below the one the cursor is on, or fill the cursor's line if it is empty."""
        if not self.need_film():
            return
        line, _ = self.current_line()
        if self.editor.GetLineText(line).strip():
            self.insert_after_line(line, text)
        else:
            self.editor.SetInsertionPoint(self.editor.XYToPosition(0, line))
            self.editor.WriteText(text)
        self.editor.SetFocus()
        self.say(f"Added: {text}")

    def on_insert_character(self, event):
        if not self.need_film():
            return
        try:
            with wx.BusyCursor():
                choices = voice_choices()
        except FilmError as e:
            self.tell(str(e))
            return
        with CharacterDialog(self, choices) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            text = dialog.line()
        # Cast lines go together: after the last one, or after the title.
        last_cast, title_line = None, None
        for i in range(self.editor.GetNumberOfLines()):
            line = self.editor.GetLineText(i).strip()
            if CAST_LINE.match(line) and not line.startswith(("[", "#")):
                last_cast = i
            elif line.lower().startswith("title:") and title_line is None:
                title_line = i
        anchor = last_cast if last_cast is not None else title_line
        if anchor is None:
            self.editor.SetInsertionPoint(0)
            self.editor.WriteText(text + "\n")
        else:
            self.insert_after_line(anchor, text)
        self.editor.SetFocus()
        self.say(f"Added to the cast: {text}")

    def on_insert_line(self, event):
        if not self.need_film():
            return
        cast = self.cast_names()
        if not cast:
            self.tell("There is nobody in the cast yet. Add a character first with Control K.")
            return
        with LineDialog(self, cast) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.insert_line(dialog.line())

    def on_insert_sound(self, event):
        if not self.need_film():
            return
        with SoundDialog(self, self.script_path.parent) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.insert_line(dialog.line())

    def on_insert_pause(self, event):
        if not self.need_film():
            return
        with wx.TextEntryDialog(self, "How many seconds should the pause be?", "Pause", "2") as d:
            if d.ShowModal() != wx.ID_OK:
                return
            value = d.GetValue().strip()
        try:
            float(value)
        except ValueError:
            self.tell("Type the number of seconds in digits, such as 2 or 0.5.", "Pause")
            return
        self.insert_line(f"[pause {value}]")

    def on_insert_stop(self, event):
        if not self.need_film():
            return
        with StopDialog(self) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.insert_line(dialog.line())

    def on_insert_scene(self, event):
        if not self.need_film():
            return
        with wx.TextEntryDialog(self, "What is the scene called? For example: The Kitchen", "Scene") as d:
            if d.ShowModal() == wx.ID_OK and d.GetValue().strip():
                self.insert_line(f"Scene: {d.GetValue().strip()}")

    # ---------- tools

    def try_voice(self, voice, text, style):
        self.say(f"Getting a sample of {voice}...")

        def done(path, error):
            if error:
                self.report("Try a voice", str(error))
            else:
                os.startfile(path)

        self.run_in_background(lambda: films.voice_sample(voice, text, style), done)

    def on_try_voice(self, event):
        dialog = FormDialog(self, "Try a voice")
        voice = dialog.field("&Voice name, such as Ryan, Sonia or Microsoft David:", wx.TextCtrl(dialog, value="Ryan"))
        words = dialog.field("&Words to say, or leave empty for a hello:", wx.TextCtrl(dialog))
        style = dialog.field("&Styles, such as whisper, echo, or leave empty:", wx.TextCtrl(dialog))
        sliders = VoiceSliders(dialog)
        dialog.finish()
        voice.SetFocus()
        with dialog:
            if dialog.ShowModal() == wx.ID_OK and voice.GetValue().strip():
                self.try_voice(voice.GetValue().strip(), words.GetValue(), join_options(style.GetValue(), sliders.text()))

    def on_word_list(self, event):
        import contextlib
        import io

        from .__main__ import cmd_words
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_words(None)
        self.report("Word list", buffer.getvalue())

    def on_shortcuts(self, event):
        self.report("Keyboard shortcuts", "\n".join([
            "Alt L: go to the film list.",
            "Alt S: go to the script.",
            "Alt G: go to the messages.",
            "Control N: new film.",
            "Control S: save the script.",
            "F5: make the film.",
            "F7: check the script for mistakes.",
            "F9: play the finished film.",
            "Control K: add a character to the cast.",
            "Control Shift K: change a character's voice, speed, pitch or volume.",
            "Control L: add a spoken line.",
            "Control B: add a sound or music.",
            "Control P: add a pause.",
            "Control T: stop sounds.",
            "Control E: mark a new scene.",
            "Control F: find. F3: find next.",
            "Control G: go to a line number.",
            "Control Shift V: try a voice.",
            "F1: syntax examples.",
            "",
            "New lines are added below the line the cursor is on.",
            "Characters are added to the end of the cast.",
        ]))


def main():
    app = wx.App()
    try:
        frame = FilmMaker()
    except Exception:
        wx.MessageBox(report_crash(), APP_NAME)
        return 1
    frame.Show()

    def crash(kind, value, tb):
        details = "".join(traceback.format_exception(kind, value, tb))
        wx.MessageBox(report_crash(details), APP_NAME, wx.OK | wx.ICON_ERROR)

    sys.excepthook = crash
    app.MainLoop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
