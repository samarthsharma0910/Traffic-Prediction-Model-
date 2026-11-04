
USE TrafficManagementDB;

-- 1. Location
CREATE TABLE Location (
    location_id INT AUTO_INCREMENT PRIMARY KEY,
    location_name VARCHAR(100) NOT NULL,
    road_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    pincode CHAR(6)
);

-- 2. Traffic Signal
CREATE TABLE Traffic_Signal (
    signal_id INT AUTO_INCREMENT PRIMARY KEY,
    location_id INT NOT NULL,
    signal_type VARCHAR(30) NOT NULL,
    signal_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    green_duration_seconds INT NOT NULL DEFAULT 30,

    FOREIGN KEY (location_id)
        REFERENCES Location(location_id),

    CHECK (signal_status IN
        ('ACTIVE', 'INACTIVE', 'MAINTENANCE')),
    CHECK (green_duration_seconds > 0)
);

-- 3. Driver
CREATE TABLE Driver (
    driver_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    license_number VARCHAR(30) NOT NULL UNIQUE,
    phone VARCHAR(15) UNIQUE
);

-- 4. Vehicle
CREATE TABLE Vehicle (
    vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
    driver_id INT NOT NULL,
    registration_number VARCHAR(20) NOT NULL UNIQUE,
    vehicle_type VARCHAR(30) NOT NULL,
    model VARCHAR(60),

    FOREIGN KEY (driver_id)
        REFERENCES Driver(driver_id)
);

-- 5. Violation Type
CREATE TABLE Violation_Type (
    violation_type_id INT AUTO_INCREMENT PRIMARY KEY,
    violation_name VARCHAR(100) NOT NULL UNIQUE,
    fine_amount DECIMAL(10,2) NOT NULL,

    CHECK (fine_amount >= 0)
);

-- 6. Traffic Officer
CREATE TABLE Traffic_Officer (
    officer_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    badge_number VARCHAR(30) NOT NULL UNIQUE,
    officer_rank VARCHAR(50) NOT NULL
);

-- 7. Traffic Violation
CREATE TABLE Traffic_Violation (
    violation_id INT AUTO_INCREMENT PRIMARY KEY,
    driver_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    violation_type_id INT NOT NULL,
    location_id INT NOT NULL,
    officer_id INT NOT NULL,
    violation_datetime DATETIME NOT NULL,
    fine_amount DECIMAL(10,2) NOT NULL,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    FOREIGN KEY (driver_id)
        REFERENCES Driver(driver_id),
    FOREIGN KEY (vehicle_id)
        REFERENCES Vehicle(vehicle_id),
    FOREIGN KEY (violation_type_id)
        REFERENCES Violation_Type(violation_type_id),
    FOREIGN KEY (location_id)
        REFERENCES Location(location_id),
    FOREIGN KEY (officer_id)
        REFERENCES Traffic_Officer(officer_id),

    CHECK (fine_amount >= 0),
    CHECK (payment_status IN
        ('PENDING', 'PAID', 'OVERDUE'))
);
    