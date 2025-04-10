import { io } from 'socket.io-client';

// Connect to the backend server
// Replace with your actual server URL - typically your backend Flask server address
const SOCKET_SERVER_URL = 'http://localhost:5001';

// Create and configure the socket
export const socket = io(SOCKET_SERVER_URL, {
  transports: ['websocket'],
  reconnection: true,
  reconnectionAttempts: 5,
  reconnectionDelay: 1000,
});

// Optional: Add connection event listeners for debugging
socket.on('connect', () => {
  console.log('Connected to gesture detection server');
});

socket.on('disconnect', () => {
  console.log('Disconnected from gesture detection server');
});

socket.on('connect_error', (error) => {
  console.error('Socket connection error:', error);
});

export default socket;