"""Explicit Windows adapters. Never accepts text, paths, shell or key names."""
import time
import psutil


class Controller:
    target = None
    locked = True

    def windows(self):
        import win32gui, win32process
        result = []
        def visit(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    exe = psutil.Process(pid).name().lower()
                    result.append((hwnd, win32gui.GetWindowText(hwnd), exe, pid))
                except (psutil.Error, OSError):
                    pass
        win32gui.EnumWindows(visit, None)
        return result

    def check(self, profile):
        import win32gui, win32process
        if not self.target:
            raise RuntimeError('no_target')
        hwnd, pid, exe = self.target
        if not win32gui.IsWindow(hwnd) or win32process.GetWindowThreadProcessId(hwnd)[1] != pid or psutil.Process(pid).name().lower() != exe:
            raise RuntimeError('target_changed')
        foreground = win32gui.GetForegroundWindow()
        # PowerPoint slideshow is a separate window in the same process.
        same_slideshow = profile == 'powerpoint' and win32process.GetWindowThreadProcessId(foreground)[1] == pid and exe == 'powerpnt.exe' and win32gui.GetClassName(foreground) == 'screenClass'
        if foreground != hwnd and not same_slideshow:
            raise RuntimeError('focus_changed')
        allowed = {
            'powerpoint': {'powerpnt.exe'}, 'pdf_edge': {'msedge.exe'},
            'pdf_acrobat': {'acrobat.exe', 'acrord32.exe'},
            'browser': {'chrome.exe', 'msedge.exe', 'firefox.exe'},
            'youtube': {'chrome.exe', 'msedge.exe', 'firefox.exe'}, 'vlc': {'vlc.exe'},
        }
        if profile in allowed and exe not in allowed[profile]:
            raise RuntimeError('profile_mismatch')
        return foreground

    def keys(self, profile, *keys):
        import win32api, win32con
        self.check(profile)
        # VK values are constants supplied by adapters only. Release modifiers even on failure.
        pressed = []
        try:
            for key in keys:
                win32api.keybd_event(key, 0, 0, 0); pressed.append(key)
        finally:
            for key in reversed(pressed):
                win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
        return 'input_dispatched_unverified'

    def powerpoint(self, action):
        import win32com.client, win32process
        app = win32com.client.GetActiveObject('PowerPoint.Application')
        if win32process.GetWindowThreadProcessId(int(app.HWND))[1] != self.target[1]:
            raise RuntimeError('com_target_mismatch')
        if action == 'start':
            app.ActivePresentation.SlideShowSettings.Run()
        else:
            if app.SlideShowWindows.Count == 0:
                if action in ('next', 'previous'):
                    view = app.ActiveWindow.View
                    current = view.Slide.SlideIndex
                    total = app.ActivePresentation.Slides.Count
                    view.GotoSlide(max(1, min(total, current + (1 if action == 'next' else -1))))
                else:
                    raise RuntimeError('slideshow_not_running')
            else:
                view = app.SlideShowWindows(1).View
                if action == 'next': view.Next()
                elif action == 'previous': view.Previous()
                elif action == 'end': view.Exit()
                elif action == 'blackout': view.State = 1 if view.State == 3 else 3
        return 'com_completed'

    def execute(self, profile, action, args):
        self.check(profile)
        if profile == 'powerpoint':
            # No silent keyboard fallback when COM fails.
            return self.powerpoint(action)
        maps = {
            'pdf_edge': {'next': (34,), 'previous': (33,), 'zoom_in': (17, 187), 'zoom_out': (17, 189)},
            'pdf_acrobat': {'next': (34,), 'previous': (33,), 'zoom_in': (17, 187), 'zoom_out': (17, 189)},
            'browser': {'scroll_up': (38,), 'scroll_down': (40,), 'back': (18, 37), 'forward': (18, 39), 'tab_next': (17, 9), 'tab_previous': (17, 16, 9), 'next': (34,), 'previous': (33,)},
        }
        if profile == 'pdf_acrobat' and action == 'page':
            self.keys(profile, 17, 16, 78)  # Acrobat Go To Page
            time.sleep(.08)
            self.keys(profile, 17, 65)
            for digit in str(args['page']):
                self.keys(profile, ord(digit))  # bounded integer only; no user-provided strings
            return self.keys(profile, 13)
        if profile in maps and action in maps[profile]:
            return self.keys(profile, *maps[profile][action])
        raise RuntimeError('unsupported')
