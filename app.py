import base64
import contextlib
import copy
import csv
import itertools
import os
import queue
import threading
import time
import traceback
from collections import Counter, deque
from datetime import datetime, timezone

import cv2 as cv
import cv2  # Ensure cv2 is also imported for direct usage
import numpy as np
import pygame
import pyttsx3
import speech_recognition as sr
import tensorflow as tf
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from gtts import gTTS
import serial  # Import the serial module

# Import the mode manager
from mode_manager import ModeManager

# from model import PointHistoryClassifier

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'  # Disable GPU
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 2 Suppress TensorFlow info messages

# Now import other dependencies

tf.get_logger().setLevel('ERROR')

app = Flask(__name__)
CORS(app)

# Configure Socket.IO with async mode
socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    # async_mode='eventlet',
                    async_mode='threading',
                    engineio_logger=False,
                    logger=False)

# Global variables for frame sharing
frame_lock = threading.Lock()
thread_lock = threading.Lock()
camera = None
preview_active = False
recording_active = False
recording_frames = []
preview_lock = threading.Lock()
recording_lock = threading.Lock()

global_vars = {
    'controller': None,
    'processing_active': False,
    'latest_gesture': "No Gesture Detected",
    'latest_confidence': 0.0,
    'current_handedness': "Unknown",
    'current_landmarks': [],
    'current_bounding_box': [0, 0, 0, 0],
    'detected_hands_count': 0,
    'current_fps': 0,
    'gesture_history': deque(maxlen=5),
    'latest_frame_base64': '',
    'mode_manager': ModeManager(),
    'current_mode': 'general_recognition'
}

with contextlib.redirect_stderr(open(os.devnull, 'w')):
    import mediapipe as mp

    from model import KeyPointClassifier, PointHistoryClassifier
    from utils import CvFpsCalc

mp_drawing = mp.solutions.drawing_utils


class VoiceAssistant:
    def __init__(self):
        # Consider using offline TTS engine for reliability
        self.engine = pyttsx3.init()  # Alternative to gTTS
        self.engine.setProperty('rate', 150)  # Better voice control
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.command_queue = queue.Queue()
        self.is_listening = False
        pygame.mixer.init()

        # Calibrate the recognizer for ambient noise
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)

        # Configure recognizer parameters
        self.recognizer.dynamic_energy_threshold = True
        # Adjust this value based on your environment
        self.recognizer.energy_threshold = 4000
        # Time of silence needed to consider the phrase complete
        self.recognizer.pause_threshold = 0.8
        self.recognizer.operation_timeout = None  # No timeout for API operations

    def start_listening(self):
        """Start listening for voice commands in a separate thread"""
        self.is_listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop_listening(self):
        """Stop listening for voice commands"""
        self.is_listening = False

    def _listen_loop(self):
        """Continuous listening loop for voice commands with improved error handling"""
        silence_counter = 0  # Track consecutive timeouts
        max_silence_count = 5  # Number of consecutive timeouts before recalibrating

        while self.is_listening:
            try:
                with self.microphone as source:
                    try:
                        # Shorter timeout to make it more responsive
                        audio = self.recognizer.listen(
                            source, timeout=1, phrase_time_limit=5)
                        silence_counter = 0  # Reset counter on successful listen

                        try:
                            command = self.recognizer.recognize_google(
                                audio).lower()
                            if command:  # Only process non-empty commands
                                self.command_queue.put(command)
                                # Debug feedback
                                print(f"Recognized command: {command}")

                        except sr.UnknownValueError:
                            # Speech was unclear - this is normal, just continue
                            pass
                        except sr.RequestError as e:
                            print(
                                f"Could not request results from speech recognition service; {e}")
                            time.sleep(1)

                    except sr.WaitTimeoutError:
                        # Handle timeout more gracefully
                        silence_counter += 1
                        if silence_counter >= max_silence_count:
                            # Recalibrate for ambient noise after several timeouts
                            print("Recalibrating for ambient noise...")
                            self.recognizer.adjust_for_ambient_noise(source)
                            silence_counter = 0

            except Exception as e:
                if not isinstance(e, sr.WaitTimeoutError):  # Only log non-timeout errors
                    print(f"Unexpected error in listen loop: {e}")
                time.sleep(0.1)  # Short sleep to prevent CPU spinning

    def speak(self, text):
        """Convert text to speech and play it with error handling"""
        try:
            tts = gTTS(text=text, lang='en')
            temp_file = "temp_speech.mp3"

            # Cleanup any existing temporary file
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass

            try:
                tts.save(temp_file)
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
            finally:
                # Cleanup in a finally block to ensure it happens
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass

        except Exception as e:
            print(f"Error in speech synthesis: {e}")


class GestureVoiceController:
    def __init__(self):
        self.voice_assistant = VoiceAssistant()
        self.current_gesture = None
        self.last_voiced_gesture = None
        self.last_command_time = 0
        self.command_cooldown = 1  # Reduced cooldown to 1 second
        self.gesture_history = deque(maxlen=5)  # Track last 5 gestures
        self.gesture_stable_count = 0  # Count consecutive same gestures
        self.min_stable_frames = 3  # Minimum consistent detections required
        self.gesture_confidence = {}  # Track confidence levels for each gesture
        self.user_preference = {}  # Store user preferences
        self.interaction_count = 0  # Count interactions for adaptive responses
        self.interaction_context = "neutral"  # Track context of interaction
        self.gesture_combo_buffer = []  # For combo gesture detection
        self.combo_timeout = 3  # Seconds to recognize a combo
        self.last_combo_time = 0


        self.button_actions = {
            0: self.toggle_voice_feedback,
            1: self.toggle_gesture_mode,
            2: self.emergency_stop
        }


        # Add haptic feedback support
        self.haptic_device = None
        self.try_connect_haptic()

        # Add ambient light control if available
        self.ambient_light = None
        self.try_connect_ambient()

        # Gesture response library with categorized responses
        self.gesture_responses = {
            "Open": {
                "casual": [
                    "Hand open, ready for action!",
                    "Palm detected. What's next?",
                    "Open hand registered."
                ],
                "professional": [
                    "Open palm gesture recognized.",
                    "Hand gesture: Open. Awaiting further input.",
                    "Open hand posture detected. System ready."
                ],
                "playful": [
                    "High five mode activated! Don't leave me hanging!",
                    "Open sesame! Your magical hand has been detected!"
                    "Jazz hands detected! 🌟 Ready to dazzle!"
                ],
                "sound": "soft_chime.wav",
                "haptic": "light_pulse",
                "light": (200, 200, 255)  # Soft blue
            },
            "Closed": {
                "casual": [
                    "Fist bump! Power move detected.",
                    "Clenched fist recognized.",
                    "Fist formed. Ready to rock?"
                ],
                "professional": [
                    "Closed hand gesture registered.",
                    "Hand posture: Closed fist. Acknowledged.",
                    "Gesture analysis: Closed hand configuration."
                ],
                "playful": [
                    "Hulk SMASH gesture detected! Impressive strength!",
                    "Fist of fury! Unleash your inner action hero!",
                    "Power fist activated! Superhero mode engaged!"
                ],
                "sound": "power_up.wav",
                "haptic": "strong_bump",
                "light": (255, 120, 120)  # Power red
            },
            # Additional gestures with similar structure...
            "Pointer": {
                "casual": [
                    "Pointing detected. What caught your eye?",
                    "Index finger extended. Targeting something?",
                    "Pointing gesture recognized."
                ],
                "professional": [
                    "Directional gesture registered: Index extended.",
                    "Pointing posture detected. Tracking vector.",
                    "Hand configuration: Pointer. Calculating trajectory."
                ],
                "playful": [
                    "ET phone home! Magical finger of destiny detected!",
                    "Pew pew! Finger laser activated! Target locked!",
                    "You're the chosen one! Your pointing finger has spoken!"
                ],
                "sound": "laser_select.wav",
                "haptic": "directional_pulse",
                "light": (255, 255, 150)  # Bright yellow
            },
            "OK": {
                "casual": [
                    "OK sign spotted. All good?",
                    "Circle of confirmation seen.",
                    "OK gesture registered. Proceeding."
                ],
                "professional": [
                    "Affirmative gesture detected: OK formation.",
                    "Hand configuration: OK. Confirmation registered.",
                    "Positive feedback gesture acknowledged."
                ],
                "playful": [
                    "Perfect circle achieved! Geometry wizardry confirmed!",
                    "OK-dokey! Your finger magic is working perfectly!",
                    "Circle of excellence formed! Achievement unlocked!"
                ],
                "sound": "positive_beep.wav",
                "haptic": "confirmation_pattern",
                "light": (100, 255, 100)  # Confirmation green
            },

            "Peace sign": {  # Added Peace sign gesture
                "casual": [
                    "Peace sign detected! ✌️",
                    "Victory gesture recognized!",
                    "Peace out! Gesture registered."
                ],
                "professional": [
                    "Peace sign gesture detected.",
                    "Hand configuration: Peace sign. Acknowledged.",
                    "Two-finger victory gesture recognized."
                ],
                "playful": [
                    "Peace and love! ✌️ Groovy gesture detected!",
                    "Victory dance time! Peace sign spotted!",
                    "Peace out, friend! Those fingers are speaking volumes!"
                ],
                "sound": "peace_chime.wav",
                "haptic": "double_pulse",
                "light": (150, 255, 150)  # Soft green
            },
            "Neutral": {
                "casual": [],
                "professional": [],
                "playful": [],
                "sound": "transition_woosh.wav",
                "haptic": None,
                "light": None
            }
        }

        # Define gesture combos for advanced interactions
        self.gesture_combos = {
            ("Peace sign", "Rock", "Open"): {
                "action": self._activate_party_mode,
                "response": "Party sequence activated! Let's get this party started!"
            },
            ("Pointer", "OK", "Pointer"): {
                "action": self._activate_precision_mode,
                "response": "Precision control mode activated. Sensitivity increased."
            }
        }

        # Contextual awareness states
        self.contexts = ["work", "gaming",
                         "presentation", "casual", "accessibility"]
        self.current_context = "casual"

        # Initialize user adaptation model
        self.user_model = {
            "response_speed": 1.0,  # Multiplier for response timing
            "verbosity": 0.5,  # 0.0 (minimal) to 1.0 (detailed)
            "formality": 0.5,  # 0.0 (casual) to 1.0 (formal)
            "preferred_gestures": Counter(),  # Track commonly used gestures
            "gesture_success_rate": {},  # Track recognition success by gesture
            "daily_usage_patterns": {},  # Track usage by hour
            "last_feedback": {}  # Store recent user feedback
        }

    def handle_button_toggle(self, button_id, state):
        if state == "ON":
            self.button_actions.get(button_id, lambda: None)()

    def toggle_voice_feedback(self):
        if self.voice_assistant.is_listening:
            self.voice_assistant.stop_listening()
            self.voice_assistant.speak("Voice feedback disabled")
        else:
            self.voice_assistant.start_listening()
            self.voice_assistant.speak("Voice feedback enabled")

    def toggle_gesture_mode(self):
        self.current_mode = "precise" if self.current_mode == "normal" else "normal"
        self.voice_assistant.speak(f"{self.current_mode.capitalize()} mode activated")

    def emergency_stop(self):
        self.voice_assistant.speak("Emergency stop activated")
        global_vars['processing_active'] = False
        # Add any additional cleanup here

    def try_connect_haptic(self):
        """Attempt to connect to haptic feedback devices if available"""
        try:
            # This would integrate with actual haptic hardware
            # self.haptic_device = HapticFeedbackDevice()
            pass
        except Exception:
            pass  # Gracefully handle missing hardware

    def try_connect_ambient(self):
        """Attempt to connect to ambient lighting if available"""
        try:
            # This would integrate with smart lighting systems
            # self.ambient_light = AmbientLightingSystem()
            pass
        except Exception:
            pass  # Gracefully handle missing hardware

    def start(self):
        """Start the voice assistant with enhanced initialization"""
        # Check time of day for contextual greeting
        current_hour = datetime.now(timezone.utc).hour

        if 5 <= current_hour < 12:
            greeting = "Good morning! Gesture control activated and ready for your input."
        elif 12 <= current_hour < 17:
            greeting = "Good afternoon! Gesture control system initialized and awaiting your commands."
        else:
            greeting = "Good evening! Gesture control system is up and running."

        # Add personalization if user data exists
        if hasattr(self, 'user_name') and self.user_name:
            greeting = f"{greeting.split('!')[0]}, {self.user_name}! {greeting.split('!')[1]}"

        # Attempt to detect environment for context awareness
        self._detect_environment_context()

        self.voice_assistant.start_listening()
        self.voice_assistant.speak(greeting)

        # Subtle ambient indication that system is ready
        self._set_ambient_state("ready")

    def stop(self):
        """Stop the voice assistant with graceful shutdown"""
        # Save user preferences before stopping
        self._save_user_preferences()

        self.voice_assistant.speak(
            "Shutting down gesture control system. Thank you for using our service.")
        self._set_ambient_state("shutdown")
        self.voice_assistant.stop_listening()

    def process_gesture(self, gesture, confidence=0.8):
        """
        Process detected hand gestures with enhanced stability checking and contextual awareness

        Args:
            gesture (str): The detected gesture name
            confidence (float): Confidence level of the detection (0.0-1.0)
        """
        current_time = time.time()
        self.current_gesture = gesture

        # Track gesture with confidence for better stability analysis
        self.gesture_history.append((gesture, confidence))

        self.socketio.emit('gesture', {
            'gesture': gesture,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'handedness': 'Right',  # Add actual handedness detection
            'landmarks': [],  # Add actual landmarks data
            'bounding_box': []  # Add actual bounding box data
        })

        # Update user model with this gesture detection
        if gesture != "Neutral":
            self.user_model["preferred_gestures"][gesture] += 1

        # Check for combo gestures
        self._check_gesture_combos(gesture, current_time)

        # Get stable gesture with confidence weighting
        stable_gesture, avg_confidence = self._get_stable_gesture()

        # Context-aware processing
        if self.current_context == "presentation" and gesture in ["Next", "Previous"]:
            # Prioritize slide navigation in presentation mode
            self._handle_presentation_control(gesture)
            self.last_voiced_gesture = gesture
            self.last_command_time = current_time
            return

        # Only process if we have a valid stable gesture with sufficient confidence
        # Note: Ensure "Peace sign" is treated like any other valid gesture
        if stable_gesture and stable_gesture != "Neutral" and avg_confidence > 0.65:
            # Check cooldown and gesture change
            time_since_last = current_time - self.last_command_time
            gesture_changed = stable_gesture != self.last_voiced_gesture

            # Adaptive cooldown based on user preference
            effective_cooldown = self.command_cooldown * \
                                 self.user_model["response_speed"]

            # Response conditions with enhanced logic:
            # 1. First gesture detection
            # 2. Gesture changed after adaptive cooldown
            # 3. Same gesture held beyond extended cooldown period
            # 4. High confidence override for critical gestures
            is_critical_gesture = stable_gesture in [
                "Stop", "Help", "Emergency"]
            confidence_override = is_critical_gesture and avg_confidence > 0.9

            if (self.last_voiced_gesture is None or
                    (gesture_changed and time_since_last >= effective_cooldown) or
                    time_since_last >= effective_cooldown * 3 or
                    confidence_override):
                self._announce_gesture(
                    stable_gesture, current_time, avg_confidence)

                # Update interaction count for adaptive responses
                self.interaction_count += 1

                # Analyze interaction pattern every 10 interactions
                if self.interaction_count % 10 == 0:
                    self._update_user_model()



    def _get_stable_gesture(self):
        """
        Determine consistent gesture from recent history with confidence weighting

        Returns:
            tuple: (stable_gesture, average_confidence)
        """
        if len(self.gesture_history) < self.min_stable_frames:
            return None, 0.0  # Not enough data

        # Extract gestures and confidences
        gestures = [g for g, _ in self.gesture_history]
        confidences = {}

        # Calculate weighted confidence for each gesture type
        for gesture, conf in self.gesture_history:
            if gesture not in confidences:
                confidences[gesture] = []
            confidences[gesture].append(conf)

        # Count occurrences with confidence weighting
        weighted_counter = Counter()
        for gesture in set(gestures):
            # Weight by both frequency and average confidence
            avg_conf = sum(confidences[gesture]) / len(confidences[gesture])
            count = gestures.count(gesture)
            weighted_counter[gesture] = count * avg_conf

        # Find most likely gesture
        if not weighted_counter:
            return "Neutral", 0.0

        most_common = weighted_counter.most_common(1)[0]
        most_common_gesture = most_common[0]

        # Calculate average confidence for this gesture
        avg_confidence = sum(confidences.get(most_common_gesture, [
            0])) / len(confidences.get(most_common_gesture, [1]))

        # Check if most common gesture meets stability threshold
        if weighted_counter[most_common_gesture] >= self.min_stable_frames * 0.6:
            return most_common_gesture, avg_confidence

        return "Neutral", 0.0  # Default to neutral if not stable

    def _announce_gesture(self, gesture, current_time, confidence):
        """
        Handle gesture announcement with contextual variations and multimodal feedback

        Args:
            gesture (str): The stable gesture to announce
            current_time (float): Current timestamp
            confidence (float): Detection confidence level
        """
        if gesture in self.gesture_responses:
            # Select appropriate response style based on user model and context
            style = self._get_response_style()

            # Get response options for this style
            responses = self.gesture_responses[gesture].get(style, [])

            if responses:
                # Select response variation based on interaction count to prevent repetition
                variation_index = self.interaction_count % len(responses)
                response = responses[variation_index]

                # Add confidence indicator for debugging/accessibility mode
                if self.current_context == "accessibility" or self.user_model["verbosity"] > 0.8:
                    confidence_str = f" Confidence: {confidence:.1%}"
                    response += confidence_str

                # Trigger multimodal feedback
                self._provide_multimodal_feedback(gesture)

                # Speak the selected response
                self.voice_assistant.speak(response)

                # Update state tracking
                self.last_voiced_gesture = gesture
                self.last_command_time = current_time
                self.gesture_history.clear()  # Reset after successful announcement

                # Log success for this gesture type
                self._update_gesture_success(gesture, True)

    def _get_response_style(self):
        """Determine appropriate response style based on context and user preferences"""
        # Default to casual style
        if self.user_model["formality"] < 0.3:
            return "playful"
        elif self.user_model["formality"] > 0.7:
            return "professional"
        else:
            return "casual"

    def draw_rounded_rectangle(img, x, y, w, h, color, corner_radius=20, thickness=-1):
        # Draw rectangles between corners
        cv.rectangle(img, (x + corner_radius, y),
                (x + w - corner_radius, y + h), color, thickness)
        cv.rectangle(img, (x, y + corner_radius),
                (x + w, y + h - corner_radius), color, thickness)

        # Draw circular corners
        for i in range(4):
            x1 = x + w - corner_radius if i % 2 else x
            y1 = y + h - corner_radius if i > 1 else y
            cv.ellipse(img, (x1, y1), (corner_radius, corner_radius),
                      i * 90, 0, 90, color, thickness)

    def _provide_multimodal_feedback(self, gesture):
        """Provide synchronized feedback across multiple channels"""
        # Get feedback patterns for this gesture
        feedback = self.gesture_responses.get(gesture, {})

        # Play sound if available
        sound_file = feedback.get("sound")
        if sound_file:
            self._play_sound_effect(sound_file)

        # Trigger haptic feedback if available
        haptic_pattern = feedback.get("haptic")
        if self.haptic_device and haptic_pattern:
            self._trigger_haptic(haptic_pattern)

        # Set ambient lighting if available
        light_color = feedback.get("light")
        if self.ambient_light and light_color:
            self._set_ambient_color(light_color)

    def _check_gesture_combos(self, gesture, current_time):
        """Check for gesture combinations/sequences"""
        # Add current gesture to combo buffer
        if gesture != "Neutral":
            self.gesture_combo_buffer.append((gesture, current_time))

        # Trim old gestures outside the combo window
        self.gesture_combo_buffer = [
            (g, t) for g, t in self.gesture_combo_buffer
            if current_time - t <= self.combo_timeout
        ]

        # Check if we have enough gestures to potentially form a combo
        if len(self.gesture_combo_buffer) >= 3:
            # Extract just the gesture names in sequence
            recent_gestures = tuple(
                g for g, _ in self.gesture_combo_buffer[-3:])

            # Check if this sequence matches any defined combo
            if recent_gestures in self.gesture_combos:
                combo_info = self.gesture_combos[recent_gestures]

                # Execute the combo action
                if combo_info["action"]:
                    combo_info["action"]()

                # Announce the combo activation
                self.voice_assistant.speak(combo_info["response"])

                # Clear the combo buffer to prevent immediate re-triggering
                self.gesture_combo_buffer.clear()
                self.last_combo_time = current_time

    def _activate_party_mode(self):
        """Example combo action: Activate party mode with visual and audio effects"""
        # This would integrate with room lighting/music systems in a real implementation
        if self.ambient_light:
            self._set_ambient_state("party")

        # Change context to reflect the party mode
        self.interaction_context = "celebration"

    def _activate_precision_mode(self):
        """Example combo action: Activate high-precision gesture control"""
        # Reduce the stability threshold for more responsive control
        self.min_stable_frames = 2

        # Increase sensitivity for detail work
        if self.haptic_device:
            self._set_haptic_sensitivity(0.8)  # Higher sensitivity

    def _update_user_model(self):
        """Analyze interaction patterns to adapt to user preferences"""
        # Update time-of-day usage pattern
        current_hour = datetime.now().hour
        self.user_model["daily_usage_patterns"][current_hour] = self.user_model["daily_usage_patterns"].get(
            current_hour, 0) + 1

        # Analyze preferred gestures
        if self.user_model["preferred_gestures"]:
            top_gestures = self.user_model["preferred_gestures"].most_common(3)

            # If user heavily favors certain gestures, reduce cooldown for those
            for gesture, count in top_gestures:
                total = sum(self.user_model["preferred_gestures"].values())
                if count / total > 0.4:  # If this gesture is used more than 40% of the time
                    # Make system more responsive to frequently used gestures
                    if gesture not in self.user_model["gesture_success_rate"]:
                        # Initialize with high expected success
                        self.user_model["gesture_success_rate"][gesture] = 0.9

        # Adapt verbosity based on interruption patterns
        if hasattr(self, 'interruption_count') and self.interruption_count > 3:
            # User frequently interrupts - they likely prefer briefer responses
            self.user_model["verbosity"] = max(
                0.2, self.user_model["verbosity"] - 0.1)
            self.interruption_count = 0

    def _update_gesture_success(self, gesture, success):
        """Track success rate of gesture recognition for adaptive thresholds"""
        if gesture not in self.user_model["gesture_success_rate"]:
            self.user_model["gesture_success_rate"][gesture] = 0.0

        # Exponential moving average (EMA) for smoothed adaptation
        alpha = 0.2  # Learning rate
        current = self.user_model["gesture_success_rate"][gesture]
        success_value = 1.0 if success else 0.0
        self.user_model["gesture_success_rate"][gesture] = current * \
                                                           (1 - alpha) + success_value * alpha

    def _detect_environment_context(self):
        """Attempt to detect the user's environment context"""
        # This would use more sensors in a real implementation
        current_hour = datetime.now().hour

        # Simple time-based context detection
        if 9 <= current_hour < 17 and datetime.now().weekday() < 5:
            self.current_context = "work"
        elif 20 <= current_hour or current_hour < 6:
            self.current_context = "casual"

        # Adjust system behavior based on detected context
        if self.current_context == "work":
            self.user_model["formality"] = 0.8  # More professional responses
            self.user_model["verbosity"] = 0.3  # More concise responses
        elif self.current_context == "casual":
            self.user_model["formality"] = 0.3  # More casual responses
            self.user_model["verbosity"] = 0.6  # More conversational

    def _save_user_preferences(self):
        """Save user preferences for future sessions"""
        # In a real implementation, this would write to a file or database
        preferences = {
            "user_model": self.user_model,
            "preferred_context": self.current_context,
            "last_session_time": time.time()
        }

        # Simulated persistence
        self.user_preference = preferences

    def process_voice_commands(self):
        """Process voice commands with enhanced context awareness and error recovery"""
        try:
            while not self.voice_assistant.command_queue.empty():
                command = self.voice_assistant.command_queue.get_nowait().lower()

                # Enhanced noise rejection with confidence scoring
                command_confidence = self._assess_command_confidence(command)
                if command_confidence < 0.6:
                    continue  # Likely noise or partial command

                # Improved command handling with cooldown check
                current_time = time.time()
                if current_time - self.last_command_time < 0.5:
                    continue  # Skip commands during cooldown period

                # Context-aware command processing
                processed = self._process_contextual_command(
                    command, current_time)
                if processed:
                    continue

                # Standard commands with enhanced feedback
                if "what gesture" in command or "current gesture" in command:
                    gesture_info = self.last_voiced_gesture or "No gesture detected"
                    if self.last_voiced_gesture:
                        # Add details based on verbosity preference
                        if self.user_model["verbosity"] > 0.7:
                            # last_time = time.strftime("%H:%M:%S", time.localtime(self.last_command_time))
                            last_time = datetime.fromtimestamp(
                                self.last_command_time).strftime("%H:%M:%S")
                            gesture_info = f"Current gesture is {gesture_info}, last detected at {last_time}"
                        else:
                            gesture_info = f"Current gesture: {gesture_info}"
                    self.voice_assistant.speak(gesture_info)

                elif "reset" in command or "clear" in command:
                    self.gesture_history.clear()
                    self.last_voiced_gesture = None
                    self.voice_assistant.speak("System reset complete")
                    self._set_ambient_state("ready")  # Visual confirmation

                elif "stop detection" in command or "end session" in command:
                    self.voice_assistant.speak(
                        "Stopping gesture detection. Thank you for using our system.")
                    self._set_ambient_state("shutdown")
                    return False

                elif "pause feedback" in command or "silent mode" in command:
                    self.command_cooldown = float('inf')
                    self.voice_assistant.speak(
                        "Voice feedback paused. Gesture recognition continues silently.")
                    # Visual indicator of silent mode
                    self._set_ambient_state("silent")

                elif "resume feedback" in command or "voice on" in command:
                    self.command_cooldown = 1 * \
                                            self.user_model["response_speed"]  # Apply user preference
                    self.voice_assistant.speak(
                        "Voice feedback resumed. I'll respond to your gestures again.")
                    self._set_ambient_state("active")

                elif "help" in command or "what can i say" in command:
                    # Adaptive help based on user experience level
                    is_new_user = self.interaction_count < 10
                    if is_new_user:
                        self._provide_detailed_help()
                    else:
                        self._provide_quick_help()

                # Mode switching commands
                elif "game mode" in command or "gaming mode" in command:
                    self._switch_context("gaming")
                    self.voice_assistant.speak(
                        "Game mode activated. Gesture sensitivity increased and shortcuts enabled.")

                elif "work mode" in command or "professional mode" in command:
                    self._switch_context("work")
                    self.voice_assistant.speak(
                        "Work mode activated. Using professional tone and reduced verbosity.")

                elif "casual mode" in command:
                    self._switch_context("casual")
                    self.voice_assistant.speak(
                        "Casual mode activated. Let's keep things relaxed!")

                # Adaptive learning commands
                elif "remember my preference" in command or "save this setting" in command:
                    self._save_user_preferences()
                    self.voice_assistant.speak(
                        "User preferences saved. I'll remember these settings for future sessions.")

                elif "reduce verbosity" in command or "be more brief" in command:
                    self.user_model["verbosity"] = max(
                        0.0, self.user_model["verbosity"] - 0.2)
                    self.voice_assistant.speak("I'll be more concise.")

                elif "increase detail" in command or "more information" in command:
                    self.user_model["verbosity"] = min(
                        1.0, self.user_model["verbosity"] + 0.2)
                    self.voice_assistant.speak(
                        "I'll provide more detailed responses going forward.")

        except queue.Empty:
            pass

        return True

    def _assess_command_confidence(self, command):
        """
        Assess how likely a voice command is to be a valid, intentional command

        Args:
            command (str): The voice command string to evaluate

        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        # This would be more sophisticated in a real system

        # Check for common command keywords
        command_keywords = ["gesture", "reset", "stop", "pause", "resume", "help",
                            "mode", "preference", "setting", "voice", "feedback"]

        # Count how many keywords are present
        keyword_count = sum(
            1 for keyword in command_keywords if keyword in command)

        # Simple heuristic: more keywords = higher confidence
        base_confidence = min(0.5 + (keyword_count * 0.1), 0.9)

        # Penalize very short commands that aren't exact matches
        if len(command) < 5 and keyword_count == 0:
            base_confidence *= 0.5

        return base_confidence

    def _process_contextual_command(self, command, current_time):
        """
        Process commands that depend on current context

        Returns:
            bool: True if command was processed contextually
        """
        # Gaming-specific commands
        if self.current_context == "gaming":
            if "quick combo" in command:
                self.voice_assistant.speak(
                    "Quick combo mode activated. Use rapid gestures for special moves.")
                self.combo_timeout = 1.5  # Shorter combo window
                return True

            elif "normalize sensitivity" in command:
                self.voice_assistant.speak(
                    "Restoring normal gesture sensitivity.")
                self.min_stable_frames = 3  # Default sensitivity
                return True

        # Presentation-specific commands
        elif self.current_context == "presentation":
            if "next slide" in command:
                # This would integrate with presentation software
                self.voice_assistant.speak("Advancing to next slide.")
                # self._send_keyboard_event("right_arrow")
                return True

            elif "previous slide" in command:
                self.voice_assistant.speak("Going back to previous slide.")
                # self._send_keyboard_event("left_arrow")
                return True

        # Accessibility-specific commands
        elif self.current_context == "accessibility":
            if "increase contrast" in command:
                self.voice_assistant.speak(
                    "Increasing visual contrast for gesture feedback.")
                # Would enhance visual feedback in real implementation
                return True

            elif "slower responses" in command:
                self.voice_assistant.speak(
                    "Slowing down response timing for better comprehension.")
                self.user_model["response_speed"] = 1.5  # 50% slower responses
                return True

        return False

    def _provide_detailed_help(self):
        """Provide comprehensive help for new users"""
        help_text = """Welcome to the Gesture Control System! Here's how to use it:

Basic commands:
- "What gesture" tells you the current recognized gesture
- "Reset" clears the gesture history
- "Pause feedback" temporarily stops voice responses
- "Resume feedback" restarts voice responses
- "Stop detection" ends the session

You can also say:
- "Game mode" to optimize for gaming
- "Work mode" for professional settings
- "Reduce verbosity" for shorter responses
- "Increase detail" for more information

Try showing different hand gestures like Open palm, Closed fist,
Pointing finger, OK sign, Peace sign, and many more!

Would you like me to demonstrate some gesture combinations?"""

        self.voice_assistant.speak(help_text)

    def _provide_quick_help(self):
        """Provide abbreviated help for experienced users"""
        quick_help = """Available commands: gesture info, reset, pause/resume feedback,
switch modes (game/work/casual), adjust verbosity, and stop detection.
Need more details on a specific feature?"""

        self.voice_assistant.speak(quick_help)

    def _switch_context(self, new_context):
        """Switch system behavior context"""
        self.current_context = new_context

        # Adjust system parameters based on context
        if new_context == "gaming":
            self.min_stable_frames = 2  # More responsive
            self.user_model["response_speed"] = 0.8  # Faster responses
            self.user_model["verbosity"] = 0.3  # Brief responses
            self._set_ambient_state("gaming")

        elif new_context == "work":
            self.min_stable_frames = 3  # Standard stability
            self.user_model["response_speed"] = 1.0  # Normal timing
            self.user_model["formality"] = 0.8  # Professional tone
            self._set_ambient_state("work")

        elif new_context == "presentation":
            self.min_stable_frames = 4  # Higher stability to prevent accidents
            self.user_model["verbosity"] = 0.2  # Minimal voice feedback
            self._set_ambient_state("presentation")

    def _set_ambient_state(self, state):
        """Set ambient lighting to indicate system state"""
        if not self.ambient_light:
            return

        # This would integrate with actual lighting systems
        states = {
            "ready": (100, 100, 255),  # Soft blue
            "active": (100, 255, 100),  # Soft green
            "silent": (80, 80, 100),  # Dim blue
            "gaming": (255, 50, 255),  # Vibrant purple
            "work": (255, 255, 200),  # Warm white
            "presentation": (50, 50, 150),  # Dim blue
            "shutdown": (0, 0, 0),  # Off
            "party": None  # Special pattern
        }

        if state == "party":
            # This would activate a color cycle pattern
            pass
        elif state in states:
            self._set_ambient_color(states[state])

    def _set_ambient_color(self, rgb_color):
        """Set ambient lighting to a specific color"""
        # This would integrate with actual lighting systems
        pass

    def _play_sound_effect(self, sound_file):
        """Play a sound effect for auditory feedback"""
        # This would integrate with audio system
        pass

    def _trigger_haptic(self, pattern):
        """Trigger a haptic feedback pattern"""
        if self.haptic_device:
            patterns = {
                "light_pulse": {"intensity": 0.3, "duration": 0.2},
                "strong_bump": {"intensity": 0.8, "duration": 0.4},
                "directional_pulse": {"intensity": 0.5, "duration": 0.3, "direction": "forward"},
                "confirmation_pattern": {"intensity": 0.4, "duration": 0.2, "repeats": 2},
            }

            if pattern in patterns:
                # This would send the pattern to actual haptic hardware
                haptic_params = patterns[pattern]
                # self.haptic_device.activate(**haptic_params)
                pass

    def _handle_presentation_control(self, gesture):
        """Handle special gestures for presentation control mode"""
        if gesture == "Next":
            # Simulate right arrow key press in presentation software
            self.voice_assistant.speak("Next slide")
            # Integration point with presentation software
            # self._send_keyboard_event("right_arrow")
            return True

        elif gesture == "Previous":
            # Simulate left arrow key press in presentation software
            self.voice_assistant.speak("Previous slide")
            # Integration point with presentation software
            # self._send_keyboard_event("left_arrow")
            return True

        elif gesture == "Start":
            # Start presentation (F5 in most presentation software)
            self.voice_assistant.speak("Starting presentation")
            # self._send_keyboard_event("F5")
            return True

        return False

    def receive_user_feedback(self, feedback_type, rating):
        """
        Process explicit user feedback to improve the system

        Args:
            feedback_type (str): Type of feedback (e.g., "speed", "accuracy")
            rating (float): User rating from 0.0 to 1.0
        """
        current_time = time.time()

        # Store feedback with timestamp
        self.user_model["last_feedback"][feedback_type] = {
            "rating": rating,
            "timestamp": current_time
        }

        # Adapt system based on feedback type
        if feedback_type == "speed":
            # Adjust response timing
            if rating < 0.3:  # User wants faster responses
                self.user_model["response_speed"] = max(
                    0.5, self.user_model["response_speed"] - 0.1)
                self.voice_assistant.speak("I'll be more responsive")
            elif rating > 0.7:  # User wants slower responses
                self.user_model["response_speed"] = min(
                    1.5, self.user_model["response_speed"] + 0.1)
                self.voice_assistant.speak("I'll slow down my responses")

        elif feedback_type == "accuracy":
            # Adjust stability requirements
            if rating < 0.3:  # Poor accuracy perception
                self.min_stable_frames += 1  # Require more stability
                self.voice_assistant.speak(
                    "I'll be more careful with gesture recognition")
            elif rating > 0.7:  # Good accuracy perception
                # Reduce required stability
                self.min_stable_frames = max(2, self.min_stable_frames - 1)

        # Save updated preferences
        self._save_user_preferences()

    def add_custom_gesture(self, gesture_name, responses=None):
        """
        Add a custom gesture response set

        Args:
            gesture_name (str): Name of the new gesture
            responses (dict, optional): Custom responses for different styles
        """
        if gesture_name in self.gesture_responses:
            self.voice_assistant.speak(
                f"Gesture {gesture_name} already exists. Updating responses.")
        else:
            self.voice_assistant.speak(f"Adding new gesture: {gesture_name}")

        # Set default responses if none provided
        if not responses:
            responses = {
                "casual": [f"{gesture_name} gesture detected."],
                "professional": [f"Gesture recognized: {gesture_name}."],
                "playful": [f"Wow! That's a {gesture_name}! Cool move!"],
                "sound": "new_gesture.wav",
                "haptic": "light_pulse",
                "light": (180, 180, 220)  # Light purple as default
            }

        # Add or update the gesture
        self.gesture_responses[gesture_name] = responses

        # Confirm addition
        self.voice_assistant.speak(
            f"Gesture {gesture_name} has been added to the recognition library.")

        # Save updated preferences
        self._save_user_preferences()

    def recognize_activity(self, motion_data):
        """
        Recognize ongoing activity to provide context awareness

        Args:
            motion_data (list): Recent motion sensor data

        Returns:
            str: Detected activity context
        """
        # This would use more sophisticated activity recognition in a real system
        # Simplified placeholder implementation

        # Check for presentation-like movements
        if self._detect_presentation_gestures(motion_data):
            return "presentation"

        # Check for gaming-like movements (rapid, repeated gestures)
        if self._detect_rapid_motion(motion_data):
            return "gaming"

        # Default to current context if no clear pattern detected
        return self.current_context

    def _detect_presentation_gestures(self, motion_data):
        """Detect presentation-like movement patterns"""
        # Simplified detection logic - would be more sophisticated in real implementation
        if not motion_data:
            return False

        # Look for relatively static position with occasional pointing
        stable_periods = 0
        pointing_gestures = 0

        for data_point in motion_data:
            if "stability" in data_point and data_point["stability"] > 0.8:
                stable_periods += 1
            if "gesture" in data_point and data_point["gesture"] == "Pointer":
                pointing_gestures += 1

        # If mostly stable with occasional pointing, likely a presentation
        return (stable_periods > len(motion_data) * 0.7 and pointing_gestures > 0)

    def _detect_rapid_motion(self, motion_data):
        """Detect rapid motion patterns typical of gaming"""
        # Simplified detection logic - would use more sophisticated analysis in real implementation
        if not motion_data or len(motion_data) < 5:
            return False

        # Count rapid transitions between gestures
        gesture_changes = 0
        last_gesture = None

        for data_point in motion_data:
            if "gesture" in data_point:
                if last_gesture and data_point["gesture"] != last_gesture:
                    gesture_changes += 1
                last_gesture = data_point["gesture"]

        # If many gesture changes in short period, likely gaming
        return gesture_changes > len(motion_data) * 0.4

    def process_interruption(self):
        """Handle user interrupting the system"""
        if not hasattr(self, 'interruption_count'):
            self.interruption_count = 0

        self.interruption_count += 1

        # Stop current speech
        self.voice_assistant.stop_speaking()

        if self.interruption_count > 2:
            # User seems frustrated with verbosity
            self.user_model["verbosity"] = max(
                0.2, self.user_model["verbosity"] - 0.1)
            self.voice_assistant.speak("I'll be more brief.")

        # Clear current operations
        self.gesture_history.clear()
        self._set_ambient_state("ready")

    def run_diagnostic(self):
        """Run system diagnostic and calibration routine"""
        self.voice_assistant.speak(
            "Starting system diagnostic. Please wait...")

        # Check component status
        components = {
            "Voice recognition": self.voice_assistant is not None,
            "Haptic feedback": self.haptic_device is not None,
            "Ambient lighting": self.ambient_light is not None,
            "User model": len(self.user_model) > 0
        }

        # Build diagnostic report
        report = "Diagnostic complete. "
        working_components = [name for name,
        status in components.items() if status]
        missing_components = [name for name,
        status in components.items() if not status]

        if working_components:
            report += f"Working components: {', '.join(working_components)}. "

        if missing_components:
            report += f"Unavailable components: {', '.join(missing_components)}. "

        # Report on user model health
        if self.interaction_count > 0:
            report += f"System has registered {self.interaction_count} interactions. "

            # Report top gestures
            if self.user_model["preferred_gestures"]:
                top_gesture = self.user_model["preferred_gestures"].most_common(1)[
                    0][0]
                report += f"Most frequent gesture: {top_gesture}. "

        self.voice_assistant.speak(report)

        # Recalibrate if needed
        if self.interaction_count > 100:
            self._recalibrate_sensitivity()

    def _recalibrate_sensitivity(self):
        """Recalibrate system sensitivity based on usage patterns"""
        # Check gesture success rates
        if self.user_model["gesture_success_rate"]:
            avg_success = sum(self.user_model["gesture_success_rate"].values()) / len(
                self.user_model["gesture_success_rate"])

            # Adjust stability requirements based on historical accuracy
            if avg_success < 0.6:  # Poor recognition history
                self.min_stable_frames = min(5, self.min_stable_frames + 1)
                self.voice_assistant.speak(
                    "Increasing gesture stability requirements for better accuracy.")
            elif avg_success > 0.85:  # Excellent recognition history
                self.min_stable_frames = max(2, self.min_stable_frames - 1)
                self.voice_assistant.speak(
                    "Decreasing gesture stability requirements for faster response.")


def get_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", help='cap width', type=int, default=960)
    parser.add_argument("--height", help='cap height', type=int, default=540)
    parser.add_argument('--use_static_image_mode', action='store_true')
    parser.add_argument("--min_detection_confidence",
                        help='min_detection_confidence', type=float, default=0.7)
    parser.add_argument("--min_tracking_confidence",
                        help='min_tracking_confidence', type=int, default=0.5)
    args = parser.parse_args()
    return args


def initialize_system():
    """Initializes the MediaPipe model, classifiers, and FPS calculator."""
    socketio.emit('system_status', 'initializing')

    try:
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )



        keypoint_classifier = KeyPointClassifier()
        point_history_classifier = PointHistoryClassifier()
        cvFpsCalc = CvFpsCalc(buffer_len=10)

        # ✅ Handle missing file and empty lines gracefully
        keypoint_classifier_labels = []
        try:
            with open('model/keypoint_classifier/keypoint_classifier_label.csv', encoding='utf-8-sig') as f:
                # Filter out empty rows and extract the first column
                keypoint_classifier_labels = []
                for row in csv.reader(f):
                    if row and len(row) > 0 and row[0].strip():  # Check if row exists, has elements, and first element is not empty
                        keypoint_classifier_labels.append(row[0])

                if not keypoint_classifier_labels:
                    raise ValueError("No valid labels found in the CSV file")

                print(f"Loaded {len(keypoint_classifier_labels)} gesture labels: {keypoint_classifier_labels}")
        except FileNotFoundError:
            print("Error: Label CSV file missing!")
            socketio.emit('system_error', {'message': 'Keypoint classifier label file missing'})
            raise RuntimeError("Keypoint classifier label file not found")
        except Exception as e:
            print(f"Error loading label file: {e}")
            socketio.emit('system_error', {'message': f'Error loading label file: {str(e)}'})
            raise RuntimeError(f"Error processing keypoint classifier labels: {str(e)}")

        return hands, keypoint_classifier, keypoint_classifier_labels, point_history_classifier, cvFpsCalc

    except Exception as e:
        print(f"System initialization error: {e}")
        socketio.emit('system_error', {'message': f'Initialization error: {str(e)}'})
        raise  # Re-raise error to stop execution


# SET UP THE CAMERA
def setup_camera(args):
    """Camera initialization with error handling"""
    if args is None or not hasattr(args, 'width') or not hasattr(args, 'height'):
        socketio.emit('camera_error', {'message': 'Invalid camera arguments'})
        raise ValueError("Invalid camera configuration parameters")

    for device_index in range(4):  # Try 0 to 3
        cap = cv.VideoCapture(device_index)
        if cap.isOpened():
            print(f"Found camera at index {device_index}")
            cap.set(cv.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, args.height)
            return cap
        cap.release()

    socketio.emit('camera_error', {'message': 'No cameras detected'})
    raise RuntimeError("No available cameras found")


def process_frames():
    """Captures and processes video frames for gesture recognition, including interactive buttons and serial communication."""
    global global_vars

    try:
        # Make sure initialize_system is actually returning all the expected values
        initialization_result = initialize_system()
        if len(initialization_result) != 5:
            print(f"System initialization error: expected 5 return values, got {len(initialization_result)}")
            socketio.emit('system_status', 'initialization_error')
            return

        hands, keypoint_classifier, keypoint_classifier_labels, point_history_classifier, cvFpsCalc = initialization_result

        try:
            args = get_args()
            cap = setup_camera(args)

            # Verify camera is properly set up
            if not cap or not cap.isOpened():
                print("Camera failed to open")
                socketio.emit('camera_error', {'message': 'Camera failed to open'})
                return

            # Set camera properties for better performance
            cap.set(cv.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv.CAP_PROP_FPS, 30)

        except Exception as e:
            print(f"Camera setup failed: {e}")
            socketio.emit('camera_error', {'message': f'Camera setup failed: {str(e)}'})
            return  # Exit safely if camera setup fails

        # Initialize serial communication
        try:
            ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=2)  # Adjust port for your system
            time.sleep(2)  # Allow time for connection to establish
            serial_connected = True
            print("Serial port connected successfully")
        except Exception as e:
            serial_connected = False
            print(f"Serial connection failed: {e}")
            socketio.emit('serial_error', {'message': f'Serial connection failed: {str(e)}'})

        # Initialize button configuration
        screen_width, screen_height = 1280, 720  # Match the camera resolution
        button_width, button_height = 200, 50
        button_margin = 20

        # Coordinates for the top row buttons
        button1_x = (screen_width - 3 * button_width - 2 * button_margin) // 2
        button2_x = button1_x + button_width + button_margin
        button3_x = button2_x + button_width + button_margin
        button_y = 20

        # Position for "Get Data" button (Centered at the bottom)
        get_data_x = (screen_width - button_width) // 2
        get_data_y = screen_height - button_height - 30

        # States of the buttons
        button_state = ["OFF", "OFF", "OFF", "GET DATA"]
        button_pressed = [False, False, False, False]
        button_toggle = [False, False, False, False]

        # Function to control LEDs via serial communication
        def control_led(button_index, state):
            if not serial_connected:
                print(f"Serial not connected, can't send command for Button {button_index + 1}")
                return

            command_map = {
                0: (b'2', b'1'),
                1: (b'3', b'4'),
                2: (b'5', b'6'),
                3: (b'7', None)  # "Get Data" button sends b'7'
            }

            # Map button indices to device names for voice feedback
            device_names = {
                0: "Light",
                1: "Fan",
                2: "Pump"
            }

            if button_index in command_map:
                command_on, command_off = command_map[button_index]
                if state == "ON" and command_on:
                    ser.write(command_on)
                    # Provide voice feedback for device turned ON
                    if button_index in device_names and global_vars['mode_manager'].is_home_automation_mode():
                        device = device_names[button_index]
                        feedback_message = f"{device} is now on"
                        # Use running instead of on for the fan
                        if button_index == 1:  # Fan
                            feedback_message = f"{device} is now running"
                        if global_vars.get('controller'):
                            global_vars['controller'].voice_assistant.speak(feedback_message)
                elif state == "OFF" and command_off:
                    ser.write(command_off)
                    # Provide voice feedback for device turned OFF
                    if button_index in device_names and global_vars['mode_manager'].is_home_automation_mode():
                        device = device_names[button_index]
                        feedback_message = f"{device} is now off"
                        if global_vars.get('controller'):
                            global_vars['controller'].voice_assistant.speak(feedback_message)

            print(f"Button {button_index + 1} sent: {state}")
            socketio.emit('button_update', {'button': button_index + 1, 'state': state})

        # Function to draw rounded rectangles for buttons
        def draw_rounded_rectangle(frame, x, y, width, height, color, thickness=2, radius=20):
            cv.ellipse(frame, (x + radius, y + radius), (radius, radius), 180, 0, 90, color, -1)
            cv.ellipse(frame, (x + width - radius, y + radius), (radius, radius), 270, 0, 90, color, -1)
            cv.ellipse(frame, (x + radius, y + height - radius), (radius, radius), 90, 0, 90, color, -1)
            cv.ellipse(frame, (x + width - radius, y + height - radius), (radius, radius), 0, 0, 90, color, -1)
            cv.rectangle(frame, (x + radius, y), (x + width - radius, y + height), color, -1)
            cv.rectangle(frame, (x, y + radius), (x + width, y + height - radius), color, -1)
            cv.rectangle(frame, (x + radius, y), (x + width - radius, y + height), (0, 0, 0), thickness)
            cv.rectangle(frame, (x, y + radius), (x + width, y + height - radius), (0, 0, 0), thickness)

        # History variables
        history_length = 16
        point_history = deque(maxlen=history_length)
        finger_gesture_history = deque(maxlen=history_length)
        gesture_history = deque(maxlen=10)

        socketio.emit('system_status', 'active')
        print("Camera successfully initialized")

        # Warm up the camera by reading a few frames
        for _ in range(5):
            cap.read()

        while global_vars['processing_active']:
            try:
                fps = cvFpsCalc.get()
                key = cv.waitKey(10)
                if key == 27:  # ESC
                    break

                # Capture frame
                ret, frame = cap.read()
                if not ret:
                    print("Error reading frame from camera")
                    socketio.emit('camera_error', {'message': 'Frame read error'})
                    # Try to reinitialize the camera
                    cap.release()
                    cap = setup_camera(args)
                    if not cap or not cap.isOpened():
                        break
                    continue

                # Flip frame and process
                frame = cv.flip(frame, 1)
                debug_frame = copy.deepcopy(frame)
                rgb_frame = cv.cvtColor(frame, cv.COLOR_BGR2RGB)

                # Hand detection
                rgb_frame.flags.writeable = False
                results = hands.process(rgb_frame)
                rgb_frame.flags.writeable = True

                # Reset values
                current_gesture = "No Gesture Detected"
                confidence = 0.0
                handedness = "Unknown"
                landmark_list = []
                brect = [0, 0, 0, 0]
                hand_count = 0

                # Always draw all buttons even if no hands are detected
                # Top row buttons
                draw_rounded_rectangle(debug_frame, button1_x, button_y, button_width, button_height,
                                      (0, 0, 255), -1)  # Red button
                draw_rounded_rectangle(debug_frame, button2_x, button_y, button_width, button_height,
                                      (0, 0, 255), -1)  # Red button
                draw_rounded_rectangle(debug_frame, button3_x, button_y, button_width, button_height,
                                      (0, 0, 255), -1)  # Red button
                # Get Data button at the bottom
                draw_rounded_rectangle(debug_frame, get_data_x, get_data_y, button_width, button_height,
                                      (0, 0, 255), -1)  # Red button

                # Display button labels centered on buttons
                font = cv.FONT_HERSHEY_SIMPLEX
                # Get text size to center text for top row buttons
                for i in range(3):
                    text_size = cv.getTextSize(button_state[i], font, 0.8, 2)[0]
                    button_x = button1_x + i * (button_width + button_margin)
                    text_x = button_x + (button_width - text_size[0]) // 2
                    text_y = button_y + (button_height + text_size[1]) // 2
                    cv.putText(debug_frame, button_state[i], (text_x, text_y), font, 0.8, (255, 255, 255), 2, cv.LINE_AA)

                # Get Data button text
                text_size = cv.getTextSize(button_state[3], font, 0.8, 2)[0]
                text_x = get_data_x + (button_width - text_size[0]) // 2
                text_y = get_data_y + (button_height + text_size[1]) // 2
                cv.putText(debug_frame, button_state[3], (text_x, text_y), font, 0.8, (255, 255, 255), 2, cv.LINE_AA)

                if results.multi_hand_landmarks:
                    hand_count = len(results.multi_hand_landmarks)
                    for hand_landmarks, handedness_info in zip(results.multi_hand_landmarks, results.multi_handedness):
                        # Extract handedness (left/right)
                        handedness = handedness_info.classification[0].label

                        # Process landmarks
                        brect = calc_bounding_rect(debug_frame, hand_landmarks)
                        landmark_list = calc_landmark_list(debug_frame, hand_landmarks)

                        # Draw hand landmarks on the debug frame
                        mp_drawing = mp.solutions.drawing_utils
                        mp_drawing.draw_landmarks(debug_frame, hand_landmarks, mp.solutions.hands.HAND_CONNECTIONS)

                        # Get the position of the tip of the index finger (landmark 8)
                        index_finger_tip = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]

                        # Get the pixel coordinates of the index finger tip
                        h, w, _ = debug_frame.shape
                        finger_x = int(index_finger_tip.x * w)
                        finger_y = int(index_finger_tip.y * h)

                        # Draw a circle at the index fingertip location
                        cv.circle(debug_frame, (finger_x, finger_y), 10, (0, 255, 0), -1)  # Green circle

                        # Only process button interactions in Home Automation mode
                        if global_vars['mode_manager'].is_home_automation_mode():
                            # Check if the finger is inside any of the button regions
                            # Top row buttons
                            for i in range(3):
                                button_x = button1_x + i * (button_width + button_margin)
                                if button_x <= finger_x <= button_x + button_width and button_y <= finger_y <= button_y + button_height:
                                    if not button_pressed[i]:
                                        # Toggle the button state (ON or OFF)
                                        button_toggle[i] = not button_toggle[i]
                                        button_state[i] = "ON" if button_toggle[i] else "OFF"
                                        control_led(i, button_state[i])  # Send command to hardware
                                        button_pressed[i] = True
                                    draw_rounded_rectangle(debug_frame, button_x, button_y, button_width, button_height, (0, 255, 0), -1)
                                    # Re-center text on green button
                                    text_size = cv.getTextSize(button_state[i], font, 0.8, 2)[0]
                                    text_x = button_x + (button_width - text_size[0]) // 2
                                    text_y = button_y + (button_height + text_size[1]) // 2
                                    cv.putText(debug_frame, button_state[i], (text_x, text_y), font, 0.8, (255, 255, 255), 2, cv.LINE_AA)
                                else:
                                    button_pressed[i] = False  # Reset button state
                        else:
                            # In General Recognition mode, just display the buttons without interaction
                            for i in range(3):
                                button_pressed[i] = False

                        # Get Data button - only interactive in Home Automation mode
                        if global_vars['mode_manager'].is_home_automation_mode():
                            if get_data_x <= finger_x <= get_data_x + button_width and get_data_y <= finger_y <= get_data_y + button_height:
                                if not button_pressed[3]:
                                    button_pressed[3] = True
                                    # Change button appearance
                                    draw_rounded_rectangle(debug_frame, get_data_x, get_data_y, button_width, button_height, (0, 255, 0), -1)
                                    text_size = cv.getTextSize("GETTING...", font, 0.8, 2)[0]
                                    text_x = get_data_x + (button_width - text_size[0]) // 2
                                    text_y = get_data_y + (button_height + text_size[1]) // 2
                                    cv.putText(debug_frame, "GETTING...", (text_x, text_y), font, 0.8, (255, 255, 255), 2, cv.LINE_AA)

                                    # Request data via serial if connected
                                    if serial_connected:
                                        try:
                                            control_led(3, "ON")  # Send command to request data
                                            time.sleep(0.1)  # Small delay to allow hardware to respond
                                            received_data = ser.readline().decode('utf-8', errors='ignore').strip()
                                            print("Received:", received_data)
                                            socketio.emit('serial_data', {'data': received_data})
                                            button_state[3] = "OK"  # Display message temporarily
                                        except Exception as e:
                                            print("Error reading serial data:", e)
                                            button_state[3] = "ERROR"
                                            socketio.emit('serial_error', {'message': f'Read error: {str(e)}'})
                                    else:
                                        button_state[3] = "NO SERIAL"
                                else:
                                    # Keep button green while pressed
                                    draw_rounded_rectangle(debug_frame, get_data_x, get_data_y, button_width, button_height, (0, 255, 0), -1)
                                    text_size = cv.getTextSize(button_state[3], font, 0.8, 2)[0]
                                    text_x = get_data_x + (button_width - text_size[0]) // 2
                                    text_y = get_data_y + (button_height + text_size[1]) // 2
                                    cv.putText(debug_frame, button_state[3], (text_x, text_y), font, 0.8, (255, 255, 255), 2, cv.LINE_AA)
                            else:
                                button_pressed[3] = False  # Reset button state
                                # Reset Get Data button to default after a short time
                                if button_state[3] != "GET DATA" and button_state[3] != "NO SERIAL":
                                    button_state[3] = "GET DATA"
                        else:
                            # In General Recognition mode, just reset the button state
                            button_pressed[3] = False

                        # Gesture classification
                        pre_processed_landmark_list = pre_process_landmark(landmark_list)
                        hand_sign_id = keypoint_classifier(pre_processed_landmark_list)

                        # Check if the hand_sign_id is valid
                        if 0 <= hand_sign_id < len(keypoint_classifier_labels):
                            current_gesture = keypoint_classifier_labels[hand_sign_id]
                            # Calculate confidence (replace with actual calculation if available)
                            confidence = max(0.7, min(0.99, 0.85 + (hand_sign_id * 0.01)))
                        else:
                            print(f"Invalid hand_sign_id: {hand_sign_id}, max index: {len(keypoint_classifier_labels)-1}")
                            current_gesture = "Unknown"
                            confidence = 0.5

                        # Process the gesture with the mode manager
                        mode_changed = global_vars['mode_manager'].process_gesture(current_gesture, confidence)
                        current_mode = global_vars['mode_manager'].get_current_mode()
                        global_vars['current_mode'] = current_mode

                        # If mode changed, notify via socketio
                        if mode_changed:
                            socketio.emit('mode_change', {'mode': current_mode})
                            print(f"Mode changed to: {current_mode}")

                        # Update controller and history
                        if global_vars.get('controller'):
                            global_vars['controller'].process_gesture(current_gesture)
                        gesture_history.append(current_gesture)

                        # Point history tracking
                        if hand_sign_id == 2:  # Point gesture
                            point_history.append(landmark_list[8] if len(landmark_list) > 8 else [0, 0])
                        else:
                            point_history.append([0, 0])

                        # Draw bounding box and landmarks
                        debug_frame = draw_bounding_rect(True, debug_frame, brect)
                        debug_frame = draw_landmarks(debug_frame, landmark_list)

                        # Add text with gesture information
                        cv.putText(debug_frame, f"{current_gesture} ({confidence:.2f})",
                                  (brect[0], brect[1] - 10), cv.FONT_HERSHEY_SIMPLEX,
                                  0.6, (0, 255, 0), 2)

                # FPS counter removed from camera frame as it's already in the UI

                # Convert frame to base64 for transmission
                # Reduce image quality for faster transmission
                encode_param = [int(cv.IMWRITE_JPEG_QUALITY), 80]
                _, buffer = cv.imencode('.jpg', debug_frame, encode_param)
                frame_base64 = base64.b64encode(buffer).decode('utf-8')

                # Update global variables safely
                with frame_lock:
                    global_vars.update({
                        'latest_gesture': current_gesture,
                        'latest_confidence': confidence,
                        'current_handedness': handedness,
                        'current_landmarks': landmark_list,
                        'current_bounding_box': brect,
                        'detected_hands_count': hand_count,
                        'current_fps': fps,
                        'gesture_history': list(gesture_history),
                        'latest_frame_base64': frame_base64,
                        'button_states': button_state,
                        'serial_connected': serial_connected,
                        'current_mode': global_vars['mode_manager'].get_current_mode()
                    })

                # Emit gesture data via WebSocket
                socketio.emit('gesture_update', {
                    "frame": frame_base64,
                    "gesture": current_gesture,
                    "confidence": confidence,
                    "handedness": handedness,
                    "hand_count": hand_count,
                    "fps": fps,
                    "timestamp": time.time(),
                    "initialized": True,
                    "system_status": "active" if global_vars['processing_active'] else "inactive",
                    "button_states": button_state,
                    "serial_connected": serial_connected,
                    "mode": global_vars['current_mode']
                })

            except Exception as e:
                print(f"Error in processing loop: {e}")
                traceback.print_exc()
                socketio.emit('camera_error', {'message': f'Processing error: {str(e)}'})
                # Short sleep to prevent error flooding
                time.sleep(0.5)

    except Exception as e:
        print(f"Camera processing error: {str(e)}")
        traceback.print_exc()
        socketio.emit('camera_error', {'message': f'Processing error: {str(e)}'})

    finally:
        # Set the processing flag to false to ensure other code knows we've stopped
        global_vars['processing_active'] = False

        # Release camera resources
        if 'cap' in locals() and cap is not None:
            if cap.isOpened():
                cap.release()
                print("Camera released")

        # Close serial connection if open
        if 'ser' in locals() and serial_connected:
            ser.close()
            print("Serial connection closed")

        if 'hands' in locals() and hands:
            hands.close()

        # Notify clients
        socketio.emit('system_status', 'inactive')
        socketio.emit('camera_error', {'message': 'Camera processing stopped'})
        print("Processing thread terminated cleanly")

# Function to draw rounded rectangles for buttons (copied from first code sample)
def draw_rounded_rectangle(frame, x, y, width, height, color, thickness=-1, radius=20):
    cv.ellipse(frame, (x + radius, y + radius), (radius, radius), 180, 0, 90, color, -1)  # Top-left corner
    cv.ellipse(frame, (x + width - radius, y + radius), (radius, radius), 270, 0, 90, color, -1)  # Top-right corner
    cv.ellipse(frame, (x + radius, y + height - radius), (radius, radius), 90, 0, 90, color, -1)  # Bottom-left corner
    cv.ellipse(frame, (x + width - radius, y + height - radius), (radius, radius), 0, 0, 90, color,
                -1)  # Bottom-right corner
    cv.rectangle(frame, (x + radius, y), (x + width - radius, y + height), color, -1)  # Top horizontal
    cv.rectangle(frame, (x, y + radius), (x + width, y + height - radius), color, -1)  # Vertical sides


def select_mode(key, mode):


    number = -1
    if 48 <= key <= 57:  # 0 ~ 9
        number = key - 48
    if key == 110:  # n
        mode = 0
    if key == 107:  # k
        mode = 1
    if key == 104:  # h
        mode = 2
    return number, mode


def calc_bounding_rect(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_array = np.empty((0, 2), int)

    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)

        landmark_point = [np.array((landmark_x, landmark_y))]

        landmark_array = np.append(landmark_array, landmark_point, axis=0)

    x, y, w, h = cv.boundingRect(landmark_array)

    return [x, y, x + w, y + h]


def calc_landmark_list(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_point = []

    # Keypoint
    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)

        landmark_point.append([landmark_x, landmark_y])

    return landmark_point


def pre_process_landmark(landmark_list):
    temp_landmark_list = copy.deepcopy(landmark_list)

    # Convert to relative coordinates
    base_x, base_y = 0, 0
    for index, landmark_point in enumerate(temp_landmark_list):
        if index == 0:
            base_x, base_y = landmark_point[0], landmark_point[1]

        temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
        temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

    # Convert to a one-dimensional list
    temp_landmark_list = list(
        itertools.chain.from_iterable(temp_landmark_list))

    # Normalization
    max_value = max(list(map(abs, temp_landmark_list)))

    # print("MV", max_value)

    def normalize_(n):
        return n / max_value

    temp_landmark_list = list(map(normalize_, temp_landmark_list))

    return temp_landmark_list


def pre_process_point_history(image, point_history):
    image_width, image_height = image.shape[1], image.shape[0]

    temp_point_history = copy.deepcopy(point_history)

    # Convert to relative coordinates
    base_x, base_y = 0, 0
    for index, point in enumerate(temp_point_history):
        if index == 0:
            base_x, base_y = point[0], point[1]

        temp_point_history[index][0] = (temp_point_history[index][0] -
                                        base_x) / image_width
        temp_point_history[index][1] = (temp_point_history[index][1] -
                                        base_y) / image_height

    # Convert to a one-dimensional list
    temp_point_history = list(
        itertools.chain.from_iterable(temp_point_history))

    return temp_point_history


def send_preview_frames():
    """Thread function to send preview frames via WebSocket"""
    while preview_active:
        ret, frame = camera.read()
        if ret:
            # Convert frame to base64
            _, buffer = cv2.imencode('.jpg', frame)
            b64_frame = base64.b64encode(buffer).decode('utf-8')

            # Send frame via WebSocket
            socketio.emit('preview_frame', {
                'frame': b64_frame,
                'timestamp': datetime.now().isoformat()
            })

            # Save frame if recording
            if recording_active:
                with recording_lock:
                    recording_frames.append(b64_frame)
                    socketio.emit('frame_captured', {
                        'count': len(recording_frames),
                        'timestamp': datetime.now().isoformat()
                    })

        time.sleep(0.033)  # ~30 FPS


def logging_csv(number, mode, landmark_list, point_history_list):
    if mode == 0:
        pass
    if mode == 1 and (0 <= number <= 9):
        csv_path = 'model/keypoint_classifier/keypoint.csv'
        with open(csv_path, 'a', newline="") as f:
            writer = csv.writer(f)
            writer.writerow([number, *landmark_list])
    if mode == 2 and (0 <= number <= 9):
        csv_path = 'model/point_history_classifier/point_history.csv'
        with open(csv_path, 'a', newline="") as f:
            writer = csv.writer(f)
            writer.writerow([number, *point_history_list])
    return

# Function to draw rounded rectangles for buttons

# Function to draw rounded rectangles for buttons
def draw_rounded_rectangle(frame, x, y, width, height, color, thickness=2, radius=20):
    cv2.ellipse(frame, (x + radius, y + radius), (radius, radius), 180, 0, 90, color, -1)  # Top-left corner
    cv2.ellipse(frame, (x + width - radius, y + radius), (radius, radius), 270, 0, 90, color, -1)  # Top-right corner
    cv2.ellipse(frame, (x + radius, y + height - radius), (radius, radius), 90, 0, 90, color, -1)  # Bottom-left corner
    cv2.ellipse(frame, (x + width - radius, y + height - radius), (radius, radius), 0, 0, 90, color,
                -1)  # Bottom-right corner
    cv2.rectangle(frame, (x + radius, y), (x + width - radius, y + height), color, -1)  # Top horizontal
    cv2.rectangle(frame, (x, y + radius), (x + width, y + height - radius), color, -1)  # Vertical sides
    cv2.rectangle(frame, (x + radius, y), (x + width - radius, y + height), (0, 0, 0),
                  thickness)  # Top horizontal border
    cv2.rectangle(frame, (x, y + radius), (x + width, y + height - radius), (0, 0, 0), thickness)  # Vertical borders
    cv2.ellipse(frame, (x + radius, y + radius), (radius, radius), 180, 0, 90, (0, 0, 0), thickness)  # Top-left border
    cv2.ellipse(frame, (x + width - radius, y + radius), (radius, radius), 270, 0, 90, (0, 0, 0),
                thickness)  # Top-right border
    cv2.ellipse(frame, (x + radius, y + height - radius), (radius, radius), 90, 0, 90, (0, 0, 0),
                thickness)  # Bottom-left border
    cv2.ellipse(frame, (x + width - radius, y + height - radius), (radius, radius), 0, 0, 90, (0, 0, 0),
                thickness)  # Bottom-right border


# def draw_rounded_rectangle(img, x, y, w, h, color, corner_radius=20, thickness=-1):
#     """Draw a rectangle with rounded corners."""
#     # Draw rectangles between corners
#     cv.rectangle(img, (x + corner_radius, y),
#                  (x + w - corner_radius, y + h), color, thickness)
#     cv.rectangle(img, (x, y + corner_radius),
#                  (x + w, y + h - corner_radius), color, thickness)

#     # Draw circular corners
#     for i in range(4):
#         x1 = x + w - corner_radius if i % 2 else x
#         y1 = y + h - corner_radius if i > 1 else y
#         cv.ellipse(img, (x1, y1), (corner_radius, corner_radius),
#                    i * 90, 0, 90, color, thickness)

#     return img



def draw_landmarks(image, landmark_point):
    if len(landmark_point) > 0:
        # Thumb
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]),
                (255, 255, 255), 2)

        # Index finger
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]),
                (255, 255, 255), 2)

        # Middle finger
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]),
                (255, 255, 255), 2)

        # Ring finger
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]),
                (255, 255, 255), 2)

        # Little finger
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]),
                (255, 255, 255), 2)

        # Palm
        cv.line(image, tuple(landmark_point[0]), tuple(
            landmark_point[1]), (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[5]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]),
                (255, 255, 255), 2)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]),
                (0, 0, 0), 6)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[0]),
                (255, 255, 255), 2)

    # Key Points
    for index, landmark in enumerate(landmark_point):
        if index == 0:  # Wrist 1
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 1:  # Wrist 2
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 2:  # Thumb: base
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 3:  # Thumb: 1st joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 4:  # Thumb: tip
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 5:  # Index: base
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 6:  # Index: 2nd joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 7:  # Index: 1st joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 8:  # Index: tip
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 9:  # Middle: base
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 10:  # Middle: 2nd joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 11:  # Middle: 1st joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 12:  # Middle: tip
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 13:  # Ring: base
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 14:  # Ring: 2nd joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 15:  # Ring: 1st joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 16:  # Ring: tip
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)
        if index == 17:  # Little: base
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 18:  # Little: 2nd joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 19:  # Little: 1st joint
            cv.circle(image, (landmark[0], landmark[1]), 5, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 5, (0, 0, 0), 1)
        if index == 20:  # Little: tip
            cv.circle(image, (landmark[0], landmark[1]), 8, (255, 255, 255),
                      -1)
            cv.circle(image, (landmark[0], landmark[1]), 8, (0, 0, 0), 1)

    return image


def draw_bounding_rect(use_brect, image, brect):
    if use_brect:
        cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[3]),
                     (0, 0, 0), 1)
    return image


def draw_info_text(image, brect, handedness, hand_sign_text,
                   finger_gesture_text=None):
    cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[1] - 22),
                 (0, 0, 0), -1)

    info_text = handedness.classification[0].label[0:]
    if hand_sign_text != "":
        info_text = info_text + ':' + hand_sign_text
    cv.putText(image, info_text, (brect[0] + 5, brect[1] - 4),
               cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv.LINE_AA)
    return image


def draw_point_history(image, point_history):
    for index, point in enumerate(point_history):
        if point[0] != 0 and point[1] != 0:
            cv.circle(image, (point[0], point[1]), 1 + int(index / 2),
                      (152, 251, 152), 2)
    return image


def draw_info(image, fps, mode, number):
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
               1.0, (0, 0, 0), 4, cv.LINE_AA)
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX,
               1.0, (255, 255, 255), 2, cv.LINE_AA)

    mode_string = ['Logging Key Point', 'Logging Point History']
    if 1 <= mode <= 2:
        cv.putText(image, "MODE:" + mode_string[mode - 1], (10, 90),
                   cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                   cv.LINE_AA)
        if 0 <= number <= 9:
            cv.putText(image, "NUM:" + str(number), (10, 110),
                       cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                       cv.LINE_AA)
    return image


# Flask Web Application
# Updated Flask routes
# @app.route('/start_detection', methods=['POST'])
# def start_detection():
#     global global_vars

#     with thread_lock:
#         if not global_vars['processing_active']:
#             # Initialize the voice controller
#             global_vars['controller'] = GestureVoiceController()
#             global_vars['controller'].start()  # Start voice assistant
#             global_vars['processing_active'] = True
#             threading.Thread(target=process_frames, daemon=True).start()
#             return jsonify({'status': 'Detection Started'})
#     return jsonify({'status': 'Detection already running'})


# @app.route('/stop_detection', methods=['POST'])
# def stop_detection():
#     global global_vars

#     if global_vars.get('controller'):
#         global_vars['controller'].stop()  # Stop voice assistant
#         global_vars['controller'] = None

#     global_vars['processing_active'] = False
#     return jsonify({'status': 'Detection Stopped'})


@app.route('/start_detection', methods=['POST'])
def start_detection():
    """Starts gesture detection processing"""
    global global_vars

    print("Start detection endpoint called")

    with thread_lock:  # ✅ Prevent multiple threads from starting
        if not global_vars['processing_active']:
            print("Starting detection process")
            global_vars['processing_active'] = True
            # Create and store the thread so we can reference it later
            process_thread = threading.Thread(target=process_frames, daemon=True)
            global_vars['process_thread'] = process_thread
            process_thread.start()  # ✅ Use daemon thread (auto-exits)
            socketio.emit('system_status', 'active')
            print("Detection process started and system_status emitted")
        else:
            print("Detection already active, not starting new thread")

    return jsonify({'status': 'Detection Started'})


# @app.route('/stop_detection', methods=['POST'])
# def stop_detection():
#     """Stops gesture detection"""
#     global global_vars
#     global_vars['processing_active'] = False

#     if global_vars['controller']:
#         global_vars['controller'].stop()

#     return jsonify({'status': 'Detection Stopped'})

@app.route('/stop_detection', methods=['POST'])
def stop_detection():
    global global_vars

    print("Stop detection endpoint called")

    # Set flag to stop processing
    global_vars['processing_active'] = False
    print("Set processing_active to False")

    # Give the thread time to clean up resources
    time.sleep(0.5)

    # Force release camera if still active
    if 'process_thread' in global_vars and global_vars['process_thread'] is not None:
        if global_vars['process_thread'].is_alive():
            print("Process thread still alive, joining with timeout")
            # Wait for thread to terminate (with timeout)
            global_vars['process_thread'].join(timeout=2.0)
        else:
            print("Process thread not alive")
    else:
        print("No process_thread in global_vars")

    # Explicitly emit a status update to all clients
    socketio.emit('system_status', 'inactive')
    print("Emitted system_status inactive")

    return jsonify({"status": "Detection Stopped"})


@app.route('/force_cleanup', methods=['POST'])
def force_cleanup():
    global global_vars

    # Set flag to stop processing
    global_vars['processing_active'] = False

    # Force release any camera resources
    for obj_name in list(cv.__dict__.keys()):
        obj = getattr(cv, obj_name)
        if hasattr(obj, 'release'):
            try:
                obj.release()
            except:
                pass

    # Notify all clients
    socketio.emit('system_status', 'inactive')

    return jsonify({"status": "Emergency Cleanup Complete"})


@app.route('/gesture-data', methods=['GET'])
def get_gesture_data():
    """Retrieves the latest gesture data"""
    global global_vars

    return jsonify({
        "gesture_id": global_vars['controller'].current_gesture_id if global_vars.get('controller') else 0,
        "gesture_name": global_vars.get('latest_gesture', 'No Gesture Detected'),
        "confidence": global_vars.get('latest_confidence', 0.0),
        "handedness": global_vars.get('current_handedness', "Unknown"),
        "landmarks": global_vars.get('current_landmarks', []),
        "bounding_box": global_vars.get('current_bounding_box', [0, 0, 0, 0]),
        "hand_count": global_vars.get('detected_hands_count', 0),
        "fps": global_vars.get('current_fps', 0),
        "timestamp": time.time(),
        "system_status": "active" if global_vars.get('processing_active', False) else "inactive",
        "gesture_history": list(global_vars.get('gesture_history', [])),
        "mode": global_vars.get('current_mode', 'general_recognition')
    })


@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            with frame_lock:
                latest_frame = global_vars.get('latest_frame_base64', None)
                if latest_frame is None:
                    continue
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame.encode('utf-8') + b'\r\n')
            time.sleep(0.033)  # ~30 FPS

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/start_preview', methods=['POST'])
def start_preview():
    """Start camera preview stream"""
    global camera, preview_active

    with preview_lock:
        if not preview_active:
            try:
                camera = cv2.VideoCapture(0)
                preview_active = True
                threading.Thread(target=send_preview_frames).start()
                return jsonify({'message': 'Preview started'}), 200
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        return jsonify({'message': 'Preview already running'}), 200


@app.route('/stop_preview', methods=['POST'])
def stop_preview():
    """Stop camera preview stream"""
    global camera, preview_active

    with preview_lock:
        if preview_active:
            preview_active = False
            camera.release()
            camera = None
        return jsonify({'message': 'Preview stopped'}), 200


@app.route('/start_gesture_recording', methods=['POST'])
def start_gesture_recording():
    """Start recording gesture frames"""
    global recording_frames, recording_active

    with recording_lock:
        if not recording_active:
            recording_frames = []
            recording_active = True
            return jsonify({
                'message': 'Recording started',
                'timestamp': datetime.now().isoformat()
            }), 200
        return jsonify({'message': 'Recording already in progress'}), 200


@app.route('/stop_gesture_recording', methods=['POST'])
def stop_gesture_recording():
    """Stop recording and process gesture"""
    global recording_active

    with recording_lock:
        recording_active = False
        return jsonify({
            'message': 'Recording stopped',
            'frame_count': len(recording_frames),
            'frames': recording_frames  # Or process frames here
        }), 200


@app.route('/set_mode', methods=['POST'])
def set_mode():
    """Explicitly set the operational mode"""
    global global_vars

    data = request.json
    mode = data.get('mode')

    if mode == 'general_recognition':
        global_vars['mode_manager'].switch_to_general_mode()
        success = True
    elif mode == 'home_automation':
        global_vars['mode_manager'].switch_to_automation_mode()
        success = True
    else:
        success = False

    current_mode = global_vars['mode_manager'].get_current_mode()
    global_vars['current_mode'] = current_mode

    # Notify all clients about the mode change
    socketio.emit('mode_change', {'mode': current_mode})

    return jsonify({
        'success': success,
        'current_mode': current_mode
    })


if __name__ == '__main__':
    # Start processing in a separate thread
    # processing_thread = threading.Thread(target=process_frames)
    # processing_thread.daemon = True
    # processing_thread.start()

    socketio.run(app, host='0.0.0.0', port=5001,
                 debug=True, use_reloader=False)