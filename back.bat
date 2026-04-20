@echo off
set folder=app
set zipname=DDS-PROJETO-COMPLETO.zip

powershell -Command "Compress-Archive -Path '%folder%','py','build.gradle.kts','settings.gradle.kts','gradle','*.json','*.properties','*.bat' -DestinationPath '%zipname%'"
echo Compactação concluída: %zipname%
pause
