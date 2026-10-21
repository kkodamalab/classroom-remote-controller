"""Windows input adapter. Implemented in Phase 3/4; fail closed until available."""
class Controller:
    target = None
    locked = True

    def windows(self):
        return []

    def execute(self, profile, action, args):
        raise RuntimeError('not_implemented')
