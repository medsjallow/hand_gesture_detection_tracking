import cv2
import mediapipe as mp
import serial
import time

# Initialize Serial communication (Change COM port and baud rate accordingly)
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=2) # Adjust for your system
time.sleep(2)  # Allow time for connection to establish

# Initialize MediaPipe Hands model
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# OpenCV for capturing the video
cap = cv2.VideoCapture(0)  # 0 for default camera

# Button properties
button_width, button_height = 200, 50
screen_width, screen_height = 640, 480  # Adjust based on your camera resolution
button_margin = 20  # Space between buttons

# Positions for control buttons (Top row)
button1_x = (screen_width - 3 * button_width - 2 * button_margin) // 2
button2_x = button1_x + button_width + button_margin
button3_x = button2_x + button_width + button_margin
button_y = 20  # Top of the screen for buttons

# Position for "Get Data" button (Centered at the bottom)
get_data_x = (screen_width - button_width) // 2
get_data_y = screen_height - button_height - 30  # 30px above the bottom

# Button states
button_state = ["OFF", "OFF", "OFF", "GET DATA"]
button_pressed = [False, False, False, False]
button_toggle = [False, False, False, False]

# Function to draw rounded rectangles for buttons
def draw_rounded_rectangle(frame, x, y, width, height, color, thickness=2, radius=20):
    cv2.ellipse(frame, (x + radius, y + radius), (radius, radius), 180, 0, 90, color, -1)
    cv2.ellipse(frame, (x + width - radius, y + radius), (radius, radius), 270, 0, 90, color, -1)
    cv2.ellipse(frame, (x + radius, y + height - radius), (radius, radius), 90, 0, 90, color, -1)
    cv2.ellipse(frame, (x + width - radius, y + height - radius), (radius, radius), 0, 0, 90, color, -1)
    cv2.rectangle(frame, (x + radius, y), (x + width - radius, y + height), color, -1)
    cv2.rectangle(frame, (x, y + radius), (x + width, y + height - radius), color, -1)
    cv2.rectangle(frame, (x + radius, y), (x + width - radius, y + height), (0, 0, 0), thickness)
    cv2.rectangle(frame, (x, y + radius), (x + width, y + height - radius), (0, 0, 0), thickness)

# Function to control the LED via serial communication
def control_led(button_index, state):
    command_map = {
        0: (b'2', b'1'),
        1: (b'3', b'4'),
        2: (b'5', b'6'),
        3: (b'7', None)  # "Get Data" button sends b'6'
    }
    
    if button_index in command_map:
        command_on, command_off = command_map[button_index]
        if state == "ON" and command_on:
            ser.write(command_on)
        elif state == "OFF" and command_off:
            ser.write(command_off)

    print(f"Button {button_index + 1} sent: {state}")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    
    frame = cv2.flip(frame, 1)  # Flip for selfie-view display
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # Get the position of the tip of the index finger (landmark 8)
            index_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            h, w, _ = frame.shape
            finger_x = int(index_finger_tip.x * w)
            finger_y = int(index_finger_tip.y * h)

            cv2.circle(frame, (finger_x, finger_y), 10, (0, 255, 0), -1)  # Green circle for finger tracking

            # Check if the finger is pressing a button
            for i, (x_pos, y_pos, label) in enumerate([
                (button1_x, button_y, "1"),
                (button2_x, button_y, "2"),
                (button3_x, button_y, "3"),
                (get_data_x, get_data_y, "Get Data")
            ]):
                if x_pos <= finger_x <= x_pos + button_width and y_pos <= finger_y <= y_pos + button_height:
                    if not button_pressed[i]:
                        button_toggle[i] = not button_toggle[i]
                        button_state[i] = "ON" if button_toggle[i] else "OFF"
                        control_led(i, button_state[i])  # Send command to NodeMCU
                        button_pressed[i] = True

                        # If "Get Data" button is pressed, receive data
                        if i == 3:
                            try:
                                received_data = ser.readline().decode('utf-8', errors='ignore').strip()
                                print("Received:", received_data)
                                button_state[i] = "OK"  # Display message
                            except Exception as e:
                                print("Error reading serial data:", e)

                    draw_rounded_rectangle(frame, x_pos, y_pos, button_width, button_height, (0, 255, 0), -1)
                else:
                    draw_rounded_rectangle(frame, x_pos, y_pos, button_width, button_height, (0, 0, 255), -1)
                    button_pressed[i] = False  # Reset button state

    # Display button states
    font = cv2.FONT_HERSHEY_SIMPLEX
    for i, (x_pos, y_pos) in enumerate([
        (button1_x, button_y),
        (button2_x, button_y),
        (button3_x, button_y),
        (get_data_x, get_data_y)
    ]):
        cv2.putText(frame, button_state[i], (x_pos + 30, y_pos + 30), font, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.imshow('Finger Tracking', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
ser.close()
