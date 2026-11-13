# Windows packaging recovery

- Installed application: Electron EXE v1.3.1
- Installed backend: Phase99 (2026-10-16)
- Frontend source: Phase98.6 (2026-10-16)
- Mobile PWA: Phase97.2
- Electron source: recovered from WindowsApp v1.7.28
- Installer scripts: historical reference only

The recovered Electron source has not yet been proven
identical to the installed app.asar.

Do not execute legacy installer scripts on an existing
installation.

Next: inspect installed app.asar, verify Electron startup,
build an isolated distribution, then test installation.
