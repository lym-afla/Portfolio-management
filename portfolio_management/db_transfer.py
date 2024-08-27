import shutil
import os
import sys

import datetime

def transfer_db(direction):
    project_db = os.path.join(os.getcwd(), 'db.sqlite3')
    local_folder = r'C:\Users\yl\OneDrive\Personal\Web development\Portfolio management database'
    if not os.path.exists(local_folder):
        local_folder = r'C:\Users\fyl\OneDrive\Personal\Web development\Portfolio management database'
    local_db = os.path.join(local_folder, 'db.sqlite3')

    if direction == 'export':
        source, destination = project_db, local_db
    elif direction == 'import':
        # Backup the existing database before importing
        backup_db = os.path.join(os.path.dirname(project_db), '..', 'db.sqlite3 (backup)')
        if os.path.exists(project_db):
            shutil.copy2(project_db, backup_db)
            print(f"Backup of the existing database created successfully at {datetime.datetime.now()}.")
        source, destination = local_db, project_db
    else:
        print("Invalid direction. Use 'export' or 'import'.")
        return

    if not os.path.exists(source):
        print(f"Source file not found: {source}")
        return

    if not os.path.exists(os.path.dirname(destination)):
        print(f"Destination folder not found: {os.path.dirname(destination)}")
        return

    shutil.copy2(source, destination)
    print(f"Database {direction}ed successfully at {datetime.datetime.now()}.")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ['export', 'import']:
        print("Usage: python db_transfer.py [export|import]")
    else:
        transfer_db(sys.argv[1])