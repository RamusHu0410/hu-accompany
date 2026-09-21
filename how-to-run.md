Run django server

cd backend
python3 manage.py runserver 0.0.0.0:8000
docker compose up -d

FOR KELVIN:
export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix vips)/lib:$DYLD_FALLBACK_LIBRARY_PATH"
python3 manage.py runserver 0.0.0.0:8000


Run backend
cd frontend
flutter run
check current address to change it in Send_Strings_2Server.dart: ipconfig getifaddr en0