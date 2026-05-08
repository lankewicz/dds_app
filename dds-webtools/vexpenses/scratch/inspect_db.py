import sqlite3

def list_tables():
    conn = sqlite3.connect('solicitacoes_saldo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    for table in tables:
        t_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {t_name}")
        count = cursor.fetchone()[0]
        print(f"Table {t_name}: {count} rows")
        
        if t_name == 'import_errors' and count > 0:
            cursor.execute(f"SELECT * FROM {t_name} ORDER BY created_at DESC LIMIT 5")
            errors = cursor.fetchall()
            print(f"Latest errors in {t_name}:")
            for err in errors:
                print(err)
    
    conn.close()

if __name__ == "__main__":
    list_tables()
