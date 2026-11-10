"""A bad source asset (a missing model, a Havok value no game defines, a collision node naming no node): the
converters raise SourceFault for it, and the caller that asked for the asset for a record counts it and goes on
without that model, as New Vegas does. Only a SourceFault is caught; a bug in the converter still ends the build.
The build's end report and stamp list every fault counted, by file.

See: docs/fork/fo4_build_speed.md#faults
"""

#: {(file, reason): None} of the faults counted this run, in the order met.
FAULTS = {}


class SourceFault(Exception):
    """A source asset the build cannot use: its file (None until a caller that knows it names it) and why."""

    def __init__(self, file, reason: str):
        """`file` (a path or None), `reason`; in args, so it pickles."""
        super().__init__(None if file is None else str(file), reason)

    @property
    def file(self) -> 'str | None':
        """The source file, or None."""
        return self.args[0]

    @property
    def reason(self) -> str:
        """Why the file cannot be used."""
        return self.args[1]

    def __str__(self) -> str:
        """'<file>: <reason>'."""
        return f'{self.file}: {self.reason}'

    def at(self, file) -> 'SourceFault':
        """This fault, naming `file` when it names no file yet."""
        return self if self.file else SourceFault(file, self.reason)


def count(fault: SourceFault) -> None:
    """Add `fault` to this run's FAULTS (once per file and reason)."""
    FAULTS[(fault.file, fault.reason)] = None


def faulted(file) -> bool:
    """Whether a fault was counted this run for `file`."""
    return any(f == str(file) for f, _ in FAULTS)


def without_fault(make, *args, **kwargs):
    """make(*args, **kwargs); None after counting the SourceFault it raises."""
    try:
        return make(*args, **kwargs)
    except SourceFault as fault:
        count(fault)
        return None


def report() -> list:
    """'source fault: <file>: <reason>' lines by file, then the count."""
    lines = [f'source fault: {file}: {reason}' for file, reason in sorted(FAULTS, key=lambda k: (k[0] or '', k[1]))]
    return lines + [f'source faults: {len(FAULTS)}']


def stamp() -> dict:
    """{'source faults': ['<file>: <reason>', ...]} for the build stamp."""
    return {'source faults': [f'{file}: {reason}' for file, reason in FAULTS]}
