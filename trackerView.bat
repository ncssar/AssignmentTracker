:: trackerView.bat
:: Windows batch script to open tracker.html in Chrome App Mode
set TRACKER_PATH=%~dp0
set TRACKER_HTML="%TRACKER_PATH%/tracker.html"
set KEY_NAME="HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
for /f "tokens=2*" %%a in ('REG QUERY %KEY_NAME% /ve') do set CHROME=%%b
"%CHROME%" --app=%TRACKER_HTML%
