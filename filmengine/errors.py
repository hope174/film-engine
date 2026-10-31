"""Friendly error types. Messages here are read by non-programmers, so keep them plain."""


class FilmError(Exception):
    """A problem we can explain to the person making the film."""


class ScriptProblem:
    def __init__(self, line_number, line_text, message):
        self.line_number = line_number
        self.line_text = line_text
        self.message = message

    def __str__(self):
        text = f"Line {self.line_number}: {self.message}"
        if self.line_text:
            text += f"\n    The line says: {self.line_text.strip()}"
        return text


class ScriptErrors(FilmError):
    """One or more problems found while reading a script."""

    def __init__(self, problems):
        self.problems = problems
        count = len(problems)
        heading = "I found 1 problem in the script." if count == 1 else f"I found {count} problems in the script."
        super().__init__(heading + "\n\n" + "\n\n".join(str(p) for p in problems))
