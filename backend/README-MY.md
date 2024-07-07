Migration

first start db and adminer docker only

visit localhost:8080 adminer delete table app

recreate table named app

go to backend/app/alembic/versions folder

clean all histories: remove __pycache__ and all versioning py files

go to terminal, cd ./backend where alembic.ini resides

run this in the terminal: 
        alembic revision --autogenerate -m "Initial migration"

in the generated versioning migation py file add: 
        "from app.models import HttpUrlType"

back to terminal, run
        "alembic upgrade head"