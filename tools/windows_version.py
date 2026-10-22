"""Generate PyInstaller's Windows version resource from the app version."""
from pathlib import Path
from desktop.version import APP_NAME, VERSION


def main():
    major, minor, patch = (int(part) for part in VERSION.split('-')[0].split('.'))
    build = int(VERSION.rsplit('.', 1)[1]) if '-' in VERSION else 0
    info = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers=({major}, {minor}, {patch}, {build}), prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'kkodamalab'),
    StringStruct('FileDescription', {APP_NAME!r}),
    StringStruct('FileVersion', {VERSION!r}),
    StringStruct('ProductVersion', {VERSION!r}),
    StringStruct('ProductName', {APP_NAME!r}),
    StringStruct('OriginalFilename', 'ClassroomRemoteController.exe')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
    Path('build').mkdir(exist_ok=True)
    Path('build/windows-version.txt').write_text(info, encoding='utf-8')


if __name__ == '__main__':
    main()
