from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Таблица номеров
    c.execute('''CREATE TABLE IF NOT EXISTS rooms
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT UNIQUE NOT NULL,
                  type TEXT NOT NULL,
                  price_per_night INTEGER NOT NULL,
                  status TEXT DEFAULT 'free',
                  floor INTEGER)''')
    
    # Таблица гостей
    c.execute('''CREATE TABLE IF NOT EXISTS guests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT NOT NULL,
                  passport TEXT UNIQUE NOT NULL,
                  phone TEXT,
                  email TEXT,
                  preferences TEXT)''')
    
    # Таблица бронирований
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  guest_id INTEGER,
                  room_id INTEGER,
                  check_in_date DATE NOT NULL,
                  check_out_date DATE NOT NULL,
                  total_price INTEGER,
                  status TEXT DEFAULT 'active',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (guest_id) REFERENCES guests (id),
                  FOREIGN KEY (room_id) REFERENCES rooms (id))''')
    
    # Таблица дополнительных услуг
    c.execute('''CREATE TABLE IF NOT EXISTS services
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  booking_id INTEGER,
                  service_name TEXT NOT NULL,
                  price INTEGER NOT NULL,
                  quantity INTEGER DEFAULT 1,
                  FOREIGN KEY (booking_id) REFERENCES bookings (id))''')
    
    # Добавляем тестовые данные если их нет
    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        # Добавляем номера
        rooms = [
            ('101', 'standard', 2500, 'free', 1),
            ('102', 'standard', 2500, 'free', 1),
            ('201', 'luxury', 5000, 'free', 2),
            ('202', 'luxury', 5000, 'free', 2),
            ('301', 'suite', 7500, 'free', 3)
        ]
        c.executemany("INSERT INTO rooms (number, type, price_per_night, status, floor) VALUES (?, ?, ?, ?, ?)", rooms)
        
        # Добавляем тестового гостя
        c.execute("INSERT INTO guests (full_name, passport, phone, email) VALUES (?, ?, ?, ?)",
                  ('Иванов Иван Иванович', '4510123456', '+79161234567', 'ivanov@mail.ru'))
    
    conn.commit()
    conn.close()

# Главная страница - панель управления
@app.route('/')
def index():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Получаем статистику
    c.execute("SELECT COUNT(*) FROM rooms WHERE status='free'")
    free_rooms = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM rooms WHERE status='occupied'")
    occupied_rooms = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM bookings WHERE status='active'")
    active_bookings = c.fetchone()[0]
    
    # Ближайшие заезды
    c.execute('''SELECT b.check_in_date, g.full_name, r.number 
                 FROM bookings b 
                 JOIN guests g ON b.guest_id = g.id 
                 JOIN rooms r ON b.room_id = r.id 
                 WHERE b.status='active' 
                 ORDER BY b.check_in_date LIMIT 5''')
    upcoming_checkins = c.fetchall()
    
    conn.close()
    
    return render_template('index.html', 
                         free_rooms=free_rooms,
                         occupied_rooms=occupied_rooms,
                         active_bookings=active_bookings,
                         upcoming_checkins=upcoming_checkins)

# Модуль бронирований
@app.route('/bookings')
def bookings():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Все активные бронирования
    c.execute('''SELECT b.id, g.full_name, r.number, b.check_in_date, 
                 b.check_out_date, b.total_price, b.status 
                 FROM bookings b 
                 JOIN guests g ON b.guest_id = g.id 
                 JOIN rooms r ON b.room_id = r.id 
                 ORDER BY b.created_at DESC''')
    all_bookings = c.fetchall()
    
    conn.close()
    return render_template('bookings.html', bookings=all_bookings)

# Поиск свободных номеров
@app.route('/search_rooms', methods=['POST'])
def search_rooms():
    check_in = request.form['check_in']
    check_out = request.form['check_out']
    room_type = request.form.get('room_type', '')
    
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Ищем свободные номера на указанные даты
    query = '''SELECT * FROM rooms 
               WHERE status = 'free' 
               AND id NOT IN (
                   SELECT room_id FROM bookings 
                   WHERE status = 'active' 
                   AND ((check_in_date BETWEEN ? AND ?) 
                   OR (check_out_date BETWEEN ? AND ?))
               )'''
    params = [check_in, check_out, check_in, check_out]
    
    if room_type:
        query += " AND type = ?"
        params.append(room_type)
    
    c.execute(query, params)
    available_rooms = c.fetchall()
    conn.close()
    
    return render_template('search_results.html', 
                         rooms=available_rooms,
                         check_in=check_in,
                         check_out=check_out)

# Создание нового бронирования
@app.route('/create_booking', methods=['POST'])
def create_booking():
    room_id = request.form['room_id']
    check_in = request.form['check_in']
    check_out = request.form['check_out']
    guest_data = {
        'full_name': request.form['full_name'],
        'passport': request.form['passport'],
        'phone': request.form['phone'],
        'email': request.form['email']
    }
    
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Проверяем существование гостя или создаем нового
    c.execute("SELECT id FROM guests WHERE passport = ?", (guest_data['passport'],))
    guest = c.fetchone()
    
    if guest:
        guest_id = guest[0]
    else:
        c.execute('''INSERT INTO guests (full_name, passport, phone, email) 
                     VALUES (?, ?, ?, ?)''',
                 (guest_data['full_name'], guest_data['passport'], 
                  guest_data['phone'], guest_data['email']))
        guest_id = c.lastrowid
    
    # Рассчитываем стоимость
    check_in_date = datetime.strptime(check_in, '%Y-%m-%d')
    check_out_date = datetime.strptime(check_out, '%Y-%m-%d')
    nights = (check_out_date - check_in_date).days
    
    c.execute("SELECT price_per_night FROM rooms WHERE id = ?", (room_id,))
    price_per_night = c.fetchone()[0]
    total_price = price_per_night * nights
    
    # Создаем бронирование
    c.execute('''INSERT INTO bookings (guest_id, room_id, check_in_date, check_out_date, total_price) 
                 VALUES (?, ?, ?, ?, ?)''',
              (guest_id, room_id, check_in, check_out, total_price))
    
    # Обновляем статус номера
    c.execute("UPDATE rooms SET status = 'booked' WHERE id = ?", (room_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('bookings'))

# Модуль гостей
@app.route('/guests')
def guests():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    c.execute('''SELECT g.*, COUNT(b.id) as stays_count 
                 FROM guests g 
                 LEFT JOIN bookings b ON g.id = b.guest_id 
                 GROUP BY g.id''')
    guests_list = c.fetchall()
    
    conn.close()
    return render_template('guests.html', guests=guests_list)

# Детальная информация о госте
@app.route('/guest/<int:guest_id>')
def guest_detail(guest_id):
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM guests WHERE id = ?", (guest_id,))
    guest = c.fetchone()
    
    c.execute('''SELECT b.*, r.number 
                 FROM bookings b 
                 JOIN rooms r ON b.room_id = r.id 
                 WHERE b.guest_id = ? 
                 ORDER BY b.check_in_date DESC''', (guest_id,))
    guest_bookings = c.fetchall()
    
    conn.close()
    return render_template('guest_detail.html', guest=guest, bookings=guest_bookings)

# Модуль номерного фонда
@app.route('/rooms')
def rooms():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM rooms ORDER BY floor, number")
    rooms_list = c.fetchall()
    
    # Группируем номера по этажам для отображения
    floors = {}
    for room in rooms_list:
        floor = room[5]  # floor
        if floor not in floors:
            floors[floor] = []
        floors[floor].append(room)
    
    conn.close()
    return render_template('rooms.html', floors=floors)

# Заселение гостя
@app.route('/check_in/<int:booking_id>')
def check_in(booking_id):
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Обновляем статус бронирования и номера
    c.execute("UPDATE bookings SET status = 'checked_in' WHERE id = ?", (booking_id,))
    
    c.execute("SELECT room_id FROM bookings WHERE id = ?", (booking_id,))
    room_id = c.fetchone()[0]
    
    c.execute("UPDATE rooms SET status = 'occupied' WHERE id = ?", (room_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('bookings'))

# Выписка гостя
@app.route('/check_out/<int:booking_id>')
def check_out(booking_id):
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Обновляем статус бронирования и номера
    c.execute("UPDATE bookings SET status = 'completed' WHERE id = ?", (booking_id,))
    
    c.execute("SELECT room_id FROM bookings WHERE id = ?", (booking_id,))
    room_id = c.fetchone()[0]
    
    c.execute("UPDATE rooms SET status = 'free' WHERE id = ?", (room_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('bookings'))

# Добавление дополнительной услуги
@app.route('/add_service', methods=['POST'])
def add_service():
    booking_id = request.form['booking_id']
    service_name = request.form['service_name']
    price = request.form['price']
    quantity = request.form.get('quantity', 1)
    
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    c.execute('''INSERT INTO services (booking_id, service_name, price, quantity) 
                 VALUES (?, ?, ?, ?)''', 
              (booking_id, service_name, price, quantity))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('bookings'))

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print(" Гостиничная система запущена!")
    print(" Открой в браузере: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True)