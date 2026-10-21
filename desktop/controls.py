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
        guard = getattr(self, 'guard', None)
        if guard:
            guard()
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
        import win32com.client, win32process, win32gui
        app = win32com.client.GetActiveObject('PowerPoint.Application')
        if win32process.GetWindowThreadProcessId(int(app.HWND))[1] != self.target[1]:
            raise RuntimeError('com_target_mismatch')
        target_window = next((app.Windows(i) for i in range(1, app.Windows.Count + 1) if int(app.Windows(i).HWND) == self.target[0]), None)
        target_show = next((app.SlideShowWindows(i) for i in range(1, app.SlideShowWindows.Count + 1) if int(app.SlideShowWindows(i).HWND) == self.target[0]), None)
        if target_window is None and target_show is None:
            raise RuntimeError('com_window_mismatch')
        presentation = (target_window or target_show).Presentation
        shows = [app.SlideShowWindows(i) for i in range(1, app.SlideShowWindows.Count + 1) if app.SlideShowWindows(i).Presentation.FullName == presentation.FullName]
        foreground = win32gui.GetForegroundWindow()
        if foreground != self.target[0] and not any(int(show.HWND) == foreground for show in shows):
            raise RuntimeError('com_presentation_mismatch')
        if action == 'start':
            presentation.SlideShowSettings.Run()
        else:
            if not shows:
                if action in ('next', 'previous') and target_window is not None:
                    view = target_window.View
                    current = view.Slide.SlideIndex
                    total = presentation.Slides.Count
                    view.GotoSlide(max(1, min(total, current + (1 if action == 'next' else -1))))
                else:
                    raise RuntimeError('slideshow_not_running')
            else:
                show = next((show for show in shows if int(show.HWND) == foreground), None)
                if show is None:
                    raise RuntimeError('slideshow_not_foreground')
                view = show.View
                if action == 'next': view.Next()
                elif action == 'previous': view.Previous()
                elif action == 'end': view.Exit()
                elif action == 'blackout': view.State = 1 if view.State == 3 else 3
        return 'com_completed'

    def execute(self, profile, action, args, authorize=None):
        # Freeze the local target selection for the entire command.
        snapshot = Controller()
        snapshot.target, snapshot.locked, snapshot.guard = self.target, self.locked, authorize
        return snapshot._execute(profile, action, args)

    def _execute(self, profile, action, args):
        self.check(profile)
        if profile == 'powerpoint':
            # No silent keyboard fallback when COM fails.
            return self.powerpoint(action)
        maps = {
            'pdf_edge': {'next': (34,), 'previous': (33,), 'zoom_in': (17, 187), 'zoom_out': (17, 189)},
            'pdf_acrobat': {'next': (34,), 'previous': (33,), 'zoom_in': (17, 187), 'zoom_out': (17, 189)},
            'browser': {'scroll_up': (38,), 'scroll_down': (40,), 'back': (18, 37), 'forward': (18, 39), 'tab_next': (17, 9), 'tab_previous': (17, 16, 9), 'next': (34,), 'previous': (33,)},
            'youtube': {'play_pause': (75,), 'seek_forward': (76,), 'seek_back': (74,), 'volume_up': (38,), 'volume_down': (40,), 'mute': (77,)},
            'vlc': {'play_pause': (32,), 'seek_forward': (18, 39), 'seek_back': (18, 37), 'volume_up': (17, 38), 'volume_down': (17, 40), 'mute': (77,)},
            'windows': {'volume_up': (175,), 'volume_down': (174,), 'mute': (173,), 'escape': (27,)},
        }
        if profile == 'pdf_acrobat' and action == 'page':
            import win32gui, win32process, win32con
            self.keys(profile, 17, 16, 78)
            time.sleep(.1)
            dialog = win32gui.GetForegroundWindow()
            if win32gui.GetClassName(dialog) != '#32770' or win32process.GetWindowThreadProcessId(dialog)[1] != self.target[1] or win32gui.GetWindow(dialog, win32con.GW_OWNER) != self.target[0]:
                raise RuntimeError('page_dialog_unrecognized')
            edits = []
            win32gui.EnumChildWindows(dialog, lambda child, _: edits.append(child) if win32gui.GetClassName(child) == 'Edit' else None, None)
            if len(edits) != 1 or win32gui.GetForegroundWindow() != dialog:
                raise RuntimeError('page_dialog_unrecognized')
            if self.guard:
                self.guard()
            win32gui.SendMessage(edits[0], win32con.WM_SETTEXT, 0, str(args['page']))
            win32gui.PostMessage(dialog, win32con.WM_COMMAND, win32con.IDOK, 0)
            return 'input_dispatched_unverified'
        if profile == 'windows' and action == 'switch_app':
            if self.locked:
                raise RuntimeError('target_locked')
            return self.keys(profile, 18, 9)
        if profile == 'mouse':
            if not self.locked:
                raise RuntimeError('mouse_requires_lock')
            return self.mouse(action, args)
        if profile in maps and action in maps[profile]:
            return self.keys(profile, *maps[profile][action])
        raise RuntimeError('unsupported')

    def mouse(self, action, args):
        import win32gui, win32api, win32con
        hwnd = self.check('mouse')
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        x, y = win32api.GetCursorPos()
        if action == 'move':
            x = max(left, min(right - 1, x + args['dx']))
            y = max(top, min(bottom - 1, y + args['dy']))
        # Do not click/scroll an overlay belonging to another window.
        under = win32gui.WindowFromPoint((x, y))
        if win32gui.GetAncestor(under, 2) != hwnd:
            raise RuntimeError('pointer_outside_target')
        self.check('mouse')
        if action == 'move':
            win32api.SetCursorPos((x, y))
        elif action in ('left', 'right'):
            down, up = (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP) if action == 'left' else (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP)
            try:
                win32api.mouse_event(down, 0, 0, 0, 0)
            finally:
                win32api.mouse_event(up, 0, 0, 0, 0)
        elif action == 'scroll':
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, args['delta'] * 120, 0)
        else:
            raise RuntimeError('unsupported')
        return 'input_dispatched_unverified'
