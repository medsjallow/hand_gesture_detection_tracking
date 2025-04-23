"""
Mode Manager for Hand Gesture Recognition System

This module manages the different operational modes of the hand gesture recognition system:
1. General Gesture Recognition Mode - Detects and classifies all predefined gestures
2. Home Automation Mode - Activated by a specific gesture, allows fingertip tracking for UI interaction
"""

class ModeManager:
    # Mode constants
    GENERAL_RECOGNITION = "general_recognition"
    HOME_AUTOMATION = "home_automation"

    def __init__(self):
        self.current_mode = self.GENERAL_RECOGNITION
        self.activation_gesture = "Rock"  # The gesture that activates home automation mode (index and pinky raised)
        self.deactivation_gesture = "Victory"  # Three fingers raised (index, middle, ring)
        self.last_gesture = None
        self.mode_change_callbacks = []
        print(f"Mode Manager initialized with activation gesture: {self.activation_gesture} and deactivation gesture: {self.deactivation_gesture}")

    def get_current_mode(self):
        """Returns the current operational mode"""
        return self.current_mode

    def is_home_automation_mode(self):
        """Returns True if currently in home automation mode"""
        return self.current_mode == self.HOME_AUTOMATION

    def is_general_recognition_mode(self):
        """Returns True if currently in general recognition mode"""
        return self.current_mode == self.GENERAL_RECOGNITION

    def switch_to_general_mode(self):
        """Explicitly switch to general recognition mode"""
        if self.current_mode != self.GENERAL_RECOGNITION:
            self.current_mode = self.GENERAL_RECOGNITION
            self._notify_mode_change()
            return True
        return False

    def switch_to_automation_mode(self):
        """Explicitly switch to home automation mode"""
        if self.current_mode != self.HOME_AUTOMATION:
            self.current_mode = self.HOME_AUTOMATION
            self._notify_mode_change()
            return True
        return False

    def process_gesture(self, gesture, confidence):
        """
        Process the detected gesture and switch modes if necessary

        Args:
            gesture (str): The detected gesture
            confidence (float): Confidence level of the detection

        Returns:
            bool: True if mode was changed, False otherwise
        """
        mode_changed = False

        # Print gesture and confidence for debugging
        print(f"Processing gesture: {gesture} with confidence: {confidence:.2f}")

        # Only switch modes if confidence is high enough
        if confidence >= 0.75:
            # Check for activation gesture to enter home automation mode
            if self.current_mode == self.GENERAL_RECOGNITION and gesture == self.activation_gesture:
                print(f"Activation gesture detected! Switching to Home Automation mode")
                self.current_mode = self.HOME_AUTOMATION
                mode_changed = True

            # Check for deactivation gesture to return to general recognition mode
            elif self.current_mode == self.HOME_AUTOMATION and gesture == self.deactivation_gesture:
                print(f"Deactivation gesture detected! Switching to General Recognition mode")
                self.current_mode = self.GENERAL_RECOGNITION
                mode_changed = True

        # Store the last gesture
        self.last_gesture = gesture

        # Notify callbacks if mode changed
        if mode_changed:
            print(f"Mode changed to: {self.current_mode}")
            self._notify_mode_change()

        return mode_changed

    def register_mode_change_callback(self, callback):
        """
        Register a callback function to be called when mode changes

        Args:
            callback (function): Function to call with the new mode as argument
        """
        if callback not in self.mode_change_callbacks:
            self.mode_change_callbacks.append(callback)

    def _notify_mode_change(self):
        """Notify all registered callbacks about the mode change"""
        for callback in self.mode_change_callbacks:
            callback(self.current_mode)
