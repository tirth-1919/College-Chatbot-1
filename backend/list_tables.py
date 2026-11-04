"""List all tables in chatbot.db"""
import sqlite3

db_path = "C:\\Users\\HP\\OneDrive\\Desktop\\chatbot 4\\backend\\chatbot.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("Tables in chatbot.db:")
for table in tables:
    print(table[0])

conn.close()
