"use client"

import { useState, useRef, useEffect, useCallback, createContext, useContext } from "react"
import axios from "axios"
import io from "socket.io-client"
import {
  Box,
  Flex,
  Heading,
  Text,
  Button,
  VStack,
  HStack,
  Grid,
  GridItem,
  Container,
  Badge,
  Divider,
  Spacer,
  useDisclosure,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  FormControl,
  FormLabel,
  Switch,
  Slider,
  SliderTrack,
  SliderFilledTrack,
  SliderThumb,
  Select,
  Tooltip,
  IconButton,
  ChakraProvider,
} from "@chakra-ui/react"
import { useTheme } from "./ThemeContext"
import DarkModeToggle from "./DarkModeToggle"
import { socket } from "./socket"

// Create AppContext for sharing state
const AppContext = createContext()

// Add this at the top of the file after the imports
const globalStyles = `
  * {
    box-sizing: border-box;
  }

  img {
    max-width: 100%;
    height: auto;
  }

  .layout-container {
    contain: layout;
    position: relative;
  }
`

// Icons unchanged...
const Icons = {
  HomeIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
      />
    </svg>
  ),
  CogIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.964m11.49-9.642l1.149-.964M7.501 19.795l.75-1.3m7.5-12.99l.75-1.3m-6.063 16.658l.26-1.477m2.605-14.772l.26-1.477m0 17.726l-.26-1.477M10.698 4.614l-.26-1.477M16.5 19.794l-.75-1.299M7.5 4.205L12 12m6.894 5.785l-1.149-.964M6.256 7.178l-1.15-.964m15.352 8.864l-1.41-.513M4.954 9.435l-1.41-.514M12.002 12l-3.75 6.495"
      />
    </svg>
  ),
  UserIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
      />
    </svg>
  ),
  MenuIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
    </svg>
  ),
  CloseIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),

  PlayIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.91 11.672a.375.375 0 010 .656l-5.603 3.113a.375.375 0 01-.557-.328V8.887c0-.286.307-.466.557-.327l5.603 3.112z"
      />
    </svg>
  ),
  PauseIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 9v6m-4.5 0V9M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  QuestionIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"
      />
    </svg>
  ),
  ChartIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
      />
    </svg>
  ),
  CameraIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"
      />
    </svg>
  ),

  RecordIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" fill="currentColor" />
    </svg>
  ),
  StopIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z"
        fill="currentColor"
      />
    </svg>
  ),
  InfoIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
      />
    </svg>
  ),
  CheckIcon: () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      width="1.25em"
      height="1.25em"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
}

// Sidebar component
const Sidebar = ({ isOpen, onClose }) => {
  const [screenSize, setScreenSize] = useState({
    isMobile: false,
    isTablet: false,
    isDesktop: true
  })
  const { isDarkMode } = useTheme()
  const bg = isDarkMode ? "gray.800" : "white"
  const borderColor = isDarkMode ? "gray.700" : "gray.200"

  useEffect(() => {
    const checkScreenSize = () => {
      const width = window.innerWidth
      setScreenSize({
        isMobile: width < 480,
        isTablet: width >= 480 && width < 992,
        isDesktop: width >= 992
      })
    }

    checkScreenSize()
    window.addEventListener("resize", checkScreenSize)

    return () => window.removeEventListener("resize", checkScreenSize)
  }, [])

  return (
    <Box
      position={screenSize.isMobile || screenSize.isTablet ? "fixed" : "sticky"}
      top="0"
      left="0"
      height={(screenSize.isMobile || screenSize.isTablet) ? "100vh" : "100%"}
      width={(screenSize.isMobile || screenSize.isTablet) ? (isOpen ? (screenSize.isMobile ? "85%" : "350px") : "0") : "300px"}
      maxWidth={(screenSize.isMobile || screenSize.isTablet) ? "85%" : "300px"}
      transition="width 0.3s ease"
      bg={bg}
      borderRight="1px"
      borderRightColor={borderColor}
      zIndex="999"
      overflowX="hidden"
      overflowY="auto"
      boxShadow={(screenSize.isMobile || screenSize.isTablet) && isOpen ? "lg" : "none"}
      display="flex"
      flexDirection="column"
    >
      {/* Close Button (for Mobile) */}
      {(screenSize.isMobile || screenSize.isTablet) && (
        <Flex justify="flex-end" p="4">
          <Box as="span" onClick={onClose} cursor="pointer">
            <Icons.CloseIcon />
          </Box>
        </Flex>
      )}

      {/* Simplified Sidebar - Only GestureApp and Dark Mode Toggle */}
      <VStack align="start" spacing="3" p="3" width="100%">
        <Flex width="100%" justify="space-between" align="center" mb="2">
          <Heading size="md">GestureApp</Heading>
          <DarkModeToggle />
        </Flex>

        {/* Instructions moved to sidebar */}
        <Box width="100%" borderWidth="1px" borderRadius="md" p="3" bg={isDarkMode ? "gray.700" : "gray.50"}>
          <VStack align="start" spacing="3" width="100%">
            <Heading size="md" borderBottom="2px" borderColor="blue.500" pb="2" width="100%">Instructions</Heading>

            <Box width="100%" p="2" borderRadius="md" bg={isDarkMode ? "gray.800" : "white"}>
              <Heading size="sm" mb="2" color="blue.500">
                1. Position Your Hand
              </Heading>
              <Text fontSize="sm" textAlign="justify" lineHeight="1.6">
                Position your hand within the camera frame, making sure it's well-lit and clearly visible.
              </Text>
            </Box>

            <Box width="100%" p="2" borderRadius="md" bg={isDarkMode ? "gray.800" : "white"}>
              <Heading size="sm" mb="2" color="blue.500">
                2. Make a Gesture
              </Heading>
              <Text fontSize="sm" textAlign="justify" lineHeight="1.6">
                Perform one of the gestures from the library. Hold the gesture steady for accurate recognition.
              </Text>
            </Box>

            <Box width="100%" p="2" borderRadius="md" bg={isDarkMode ? "gray.800" : "white"}>
              <Heading size="sm" mb="2" color="blue.500">
                3. See Results
              </Heading>
              <Text fontSize="sm" textAlign="justify" lineHeight="1.6">
                The system will identify your gesture and display the result with confidence level in real-time.
              </Text>
            </Box>

            <Box width="100%" p="2" borderRadius="md" bg={isDarkMode ? "gray.800" : "white"}>
              <Heading size="sm" mb="2" color="blue.500">
                4. Create Custom Gestures
              </Heading>
              <Text fontSize="sm" textAlign="justify" lineHeight="1.6">
                Train the system to recognize your own custom gestures by using the Gesture Library feature.
              </Text>
            </Box>
          </VStack>
        </Box>
      </VStack>
    </Box>
  )
}

// Settings Modal Component
const SettingsModal = ({ isOpen, onClose, settings, updateSettings }) => {
  const { isDarkMode } = useTheme()
  const [localSettings, setLocalSettings] = useState(settings)

  // Update local settings
  const handleSettingChange = (key, value) => {
    setLocalSettings({
      ...localSettings,
      [key]: value,
    })
  }

  // Save changes
  const saveSettings = () => {
    updateSettings(localSettings)
    onClose()
  }

  // // Add new switch controls
  // <FormControl display="flex" alignItems="center">
  //   <FormLabel htmlFor="button-controls" mb="0">
  //     Enable Virtual Buttons
  //   </FormLabel>
  //   <Switch
  //     id="button-controls"
  //     isChecked={localSettings.enableButtons}
  //     onChange={(e) => handleSettingChange('enableButtons', e.target.checked)}
  //   />
  // </FormControl>

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <ModalOverlay />
      <ModalContent bg={isDarkMode ? "gray.800" : "white"}>
        <ModalHeader>System Settings</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4} align="stretch">
            <FormControl display="flex" alignItems="center">
              <FormLabel htmlFor="show-confidence" mb="0">
                Show Confidence Percentage
              </FormLabel>
              <Switch
                id="show-confidence"
                isChecked={localSettings.showConfidence}
                onChange={(e) => handleSettingChange("showConfidence", e.target.checked)}
              />
            </FormControl>

            <FormControl display="flex" alignItems="center">
              <FormLabel htmlFor="show-fps" mb="0">
                Show FPS Counter
              </FormLabel>
              <Switch
                id="show-fps"
                isChecked={localSettings.showFps}
                onChange={(e) => handleSettingChange("showFps", e.target.checked)}
              />
            </FormControl>

            <FormControl>
              <FormLabel>Detection Sensitivity</FormLabel>
              <Slider
                id="sensitivity-slider"
                defaultValue={localSettings.sensitivity}
                min={1}
                max={10}
                step={1}
                onChange={(val) => handleSettingChange("sensitivity", val)}
              >
                <SliderTrack>
                  <SliderFilledTrack />
                </SliderTrack>
                <SliderThumb boxSize={6}>
                  <Box color="blue.500" as={Icons.CogIcon} />
                </SliderThumb>
              </Slider>
              <Flex justify="space-between">
                <Text fontSize="xs">Low</Text>
                <Text fontSize="xs">High</Text>
              </Flex>
            </FormControl>

            <FormControl>
              <FormLabel>Camera Resolution</FormLabel>
              <Select
                value={localSettings.resolution}
                onChange={(e) => handleSettingChange("resolution", e.target.value)}
              >
                <option value="low">Low (480p)</option>
                <option value="medium">Medium (720p)</option>
                <option value="high">High (1080p)</option>
              </Select>
            </FormControl>
          </VStack>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            Cancel
          </Button>
          <Button colorScheme="blue" onClick={saveSettings}>
            Save Changes
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  )
}



const CameraFeed = ({ isStreaming, error, imgRef }) => {
  const socketRef = useRef(socket);
  // Local state for button states with memoized setter to prevent unnecessary re-renders
  // We only need the setter function for the socket events
  const [, setButtonStates] = useState({
    button1: false,
    button2: false,
    button3: false,
  });

  // Connect WebSocket events for gesture data and button updates
  useEffect(() => {
    // Store a reference to the socket that won't change during cleanup
    const currentSocket = socketRef.current;

    // Handle button updates from the server
    const handleButtonUpdate = (data) => {
      const { button, state } = data;
      setButtonStates((prev) => ({
        ...prev,
        [`button${button}`]: state === "ON",
      }));
    };

    // Handle full gesture updates that include button states
    const handleGestureUpdate = (data) => {
      if (data.button_states && Array.isArray(data.button_states)) {
        // Convert array ["OFF", "OFF", "OFF"] to object {button1: false, button2: false, button3: false}
        setButtonStates({
          button1: data.button_states[0] === "ON",
          button2: data.button_states[1] === "ON",
          button3: data.button_states[2] === "ON",
        });
      }

      // Update the camera feed image
      if (data.frame && imgRef.current) {
        imgRef.current.src = `data:image/jpeg;base64,${data.frame}`;
      }
    };

    currentSocket.on("button_update", handleButtonUpdate);
    currentSocket.on("gesture_update", handleGestureUpdate);

    return () => {
      // Use the stored reference in cleanup to avoid the exhaustive-deps warning
      currentSocket.off("button_update", handleButtonUpdate);
      currentSocket.off("gesture_update", handleGestureUpdate);
    };
  }, [imgRef]); // socketRef is intentionally omitted as we're using a local reference

  // Container with aspect ratio matching the backend camera (1280x720)
  return (
    <Box
      position="relative"
      borderRadius="lg"
      overflow="hidden"
      bg="black"
      width="100%"
      // Set a consistent aspect ratio using paddingBottom
      // 56.25% = (9/16 * 100) to maintain 16:9 aspect ratio (720/1280)
      pb="56.25%"
      style={{ contain: "layout" }}
    >
      {/* Image with absolute positioning to fill the container exactly */}
      <img
        ref={imgRef}
        alt="Camera Feed"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover", // Changed from contain to cover to fill exactly
          borderRadius: "lg",
          opacity: isStreaming ? 1 : 0,
          transition: "opacity 0.3s ease",
        }}
      />

      {/* Overlay when not streaming */}
      <Flex
        position="absolute"
        top="0"
        left="0"
        right="0"
        bottom="0"
        justify="center"
        align="center"
        bg="blackAlpha.700"
        color="white"
        zIndex="5"
        opacity={isStreaming ? 0 : 1}
        pointerEvents={isStreaming ? "none" : "auto"}
        transition="opacity 0.3s ease"
      >
        <VStack>
          <Icons.CameraIcon />
          <Text>Ready to detect gestures</Text>
        </VStack>
      </Flex>

      {/* Error message */}
      {error && (
        <Badge
          position="absolute"
          bottom="4"
          left="50%"
          transform="translateX(-50%)"
          colorScheme="red"
          p="2"
          fontSize="md"
          zIndex="10"
        >
          Error: {error}
        </Badge>
      )}

      {/* Virtual Buttons Overlay
      <Flex position="absolute" top="4" left="50%" transform="translateX(-50%)" gap="4" zIndex="10">
        {[1, 2, 3].map((btnNum) => (
          <Button
            key={btnNum}
            variant="ghost"
            colorScheme={buttonStates[`button${btnNum}`] ? "green" : "red"}
            opacity="0.9"
            _hover={{ opacity: 1 }}
            _before={{
              content: '""',
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              width: "100%",
              height: "100%",
              borderRadius: "md",
              bg: buttonStates[`button${btnNum}`] ? "green.500" : "red.500",
              opacity: 0.1,
              zIndex: -1,
            }}
          >
            <Box as="span" position="relative" zIndex="1">
              {btnNum === 1 && "Control"}
              {btnNum === 2 && "Mode"}
              {btnNum === 3 && "Stop"}
              <Badge ml="2" colorScheme={buttonStates[`button${btnNum}`] ? "green" : "red"} fontSize="0.6em">
                {buttonStates[`button${btnNum}`] ? "ON" : "OFF"}
              </Badge>
            </Box>
          </Button>
        ))}
      </Flex> */}
    </Box>
  );
};

const GestureDataDisplay = ({ gestureData, buttonStates }) => {
  const { currentMode } = useContext(AppContext) || { currentMode: 'general_recognition' };
  const { isDarkMode } = useTheme()
  const borderColor = isDarkMode ? "gray.700" : "gray.200"
  const textColorValue = isDarkMode ? "gray.300" : "gray.600" // Use this for text color

  return (
    <VStack spacing={2} align="space-" h="100%" p={0}>
      <Heading size="md" mb={2} px={2} pt={2}>
        Live Gesture Data
      </Heading>
      <Divider mx={0} />

      <Box px={2} pt={1}>
        <Text fontWeight="bold" fontSize="md">
          Current Mode:
        </Text>
        <Badge
          colorScheme={currentMode === 'home_automation' ? "purple" : "blue"}
          p={2}
          fontSize="sm"
          mt={1}
          width="100%"
          textAlign="center"
          display="block"
        >
          {currentMode === 'home_automation' ? 'Home Automation Mode' : 'General Recognition Mode'}
        </Badge>
      </Box>

      <Box px={2} pt={1}>
        <Text fontWeight="bold" fontSize="md">
          Detected Gesture:
        </Text>
        <Badge colorScheme="green" p={2} fontSize="sm" mt={1} width="100%" textAlign="center" display="block">
          {gestureData.gesture}
        </Badge>
      </Box>

      <Grid templateColumns={{ base: "1fr", sm: "repeat(2, 1fr)" }} gap={2} px={2}>
        <Box p={2} borderWidth="1px" borderRadius="md" borderColor={borderColor}>
          <Text fontWeight="semibold" mb={1}>
            Confidence
          </Text>
          <Text fontSize="md">{(gestureData.confidence * 100).toFixed(1)}%</Text>
        </Box>

        <Box p={2} borderWidth="1px" borderRadius="md" borderColor={borderColor}>
          <Text fontWeight="semibold" mb={1}>
            Handedness
          </Text>
          <Text fontSize="md">{gestureData.handedness}</Text>
        </Box>

        <Box p={2} borderWidth="1px" borderRadius="md" borderColor={borderColor}>
          <Text fontWeight="semibold" mb={1}>
            Hand Count
          </Text>
          <Text fontSize="md">{gestureData.hand_count}</Text>
        </Box>

        <Box p={2} borderWidth="1px" borderRadius="md" borderColor={borderColor}>
          <Text fontWeight="semibold" mb={1}>
            FPS
          </Text>
          <Text fontSize="md">{gestureData.fps.toFixed(2)}</Text>
        </Box>
      </Grid>

      <Box mt={2} px={2}>
        <Text fontSize="sm" color={textColorValue}>
          Try different gestures to see how accurately they're detected. Move your hand for optimal visibility.
        </Text>
      </Box>
      <Box p={2} borderWidth="1px" borderRadius="md" borderColor={borderColor} mx={2}>
        <Text fontWeight="semibold" mb={1}>
          Status Controls
        </Text>
        <VStack spacing={2} width="100%">
          {Object.entries(buttonStates).map(([key, value]) => (
            <Button
              key={key}
              size="sm"
              variant="outline"
              colorScheme={value ? "green" : "red"}
              leftIcon={<Box w="8px" h="8px" borderRadius="full" bg={value ? "green.500" : "red.500"} />}
              mb={1}
              isActive={value}
              _active={{ bg: value ? "green.100" : "red.100" }}
              width="100%"
            >
              {key === "button1" ? "Fan" : key === "button2" ? "Pump" : "Light"}: {value ? "Active" : "Inactive"}
            </Button>
          ))}
        </VStack>
      </Box>
    </VStack>
  )
}

// Instructions Component has been moved directly into the Sidebar

// GestureCard Component
const GestureCard = ({ title, description, children, image }) => {
  const { isDarkMode } = useTheme()
  const bg = isDarkMode ? "gray.700" : "white"
  const textColor = isDarkMode ? "gray.300" : "gray.600"
  const accentColor = "blue.500"

  return (
    <Box
      borderWidth="1px"
      borderRadius="lg"
      overflow="hidden"
      bg={bg}
      boxShadow="md"
      transition="all 0.3s ease"
      _hover={{ transform: "translateY(-5px)", boxShadow: "lg", borderColor: accentColor }}
      position="relative"
    >
      {/* Image Container with Overlay */}
      <Box h="160px" bg={isDarkMode ? "gray.600" : "gray.100"} position="relative" overflow="hidden">
        {children ? (
          <Flex h="100%" justify="center" align="center" p="4">
            {children}
          </Flex>
        ) : image ? (
          <>
            <Box
              as="img"
              src={image}
              alt={title}
              objectFit="cover"
              w="100%"
              h="100%"
              transition="transform 0.3s ease"
              _groupHover={{ transform: "scale(1.05)" }}
            />
            <Box
              position="absolute"
              top="0"
              left="0"
              right="0"
              bottom="0"
              bg="blackAlpha.300"
              opacity="0"
              transition="opacity 0.3s ease"
              _groupHover={{ opacity: 1 }}
            />
          </>
        ) : (
          <Flex h="100%" justify="center" align="center">
            <Icons.CameraIcon />
          </Flex>
        )}
      </Box>

      {/* Content */}
      <Box p="4">
        <Heading size="md" mb="2" color={isDarkMode ? "blue.300" : "blue.600"}>
          {title}
        </Heading>
        <Text fontSize="sm" color={textColor} textAlign="justify" lineHeight="1.6">
          {description}
        </Text>
      </Box>

      {/* Badge in corner */}
      <Badge
        position="absolute"
        top="2"
        right="2"
        colorScheme="blue"
        variant="solid"
        fontSize="xs"
        borderRadius="full"
        px="2"
      >
        Gesture
      </Badge>
    </Box>
  )
}

// Main App Component
const App = () => {
  // State for responsive design
  const [isSidebarOpen, setSidebarOpen] = useState(false)
  const [screenSize, setScreenSize] = useState({
    isMobile: false,
    isTablet: false,
    isDesktop: true
  })

  // Current mode state
  const [currentMode, setCurrentMode] = useState('general_recognition')

  // Theme state
  const { isDarkMode } = useTheme()

  // Modal state
  const { isOpen: isSettingsOpen, onOpen: onSettingsOpen, onClose: onSettingsClose } = useDisclosure()

  // Button states
  const [buttonStates, setButtonStates] = useState({
    button1: false,
    button2: false,
    button3: false,
  })

  // Camera and gesture detection state
  const [isStreaming, setIsStreaming] = useState(false)
  const [gestureData, setGestureData] = useState({
    gesture: "No Gesture Detected",
    confidence: 0.0,
    handedness: "Unknown",
    hand_count: 0,
    fps: 0,
    current_fps: 0,
  })
  const [error, setError] = useState(null)
  const imgRef = useRef(null)
  const socketRef = useRef(null)

  // System settings
  const [settings, setSettings] = useState({
    showConfidence: true,
    showFps: true,
    sensitivity: 5,
    enableButtons: true,
    resolution: "medium",
  })

  // Color values for dark/light mode
  const bgColor = isDarkMode ? "gray.900" : "gray.50"
  const headerBg = isDarkMode ? "gray.800" : "white"
  const borderColor = isDarkMode ? "gray.700" : "gray.200"

  // Backend server URL
  const FLASK_SERVER = "http://localhost:5001"

  // Function to stop gesture detection - defined early to be used in useEffect
  const stopDetection = useCallback(async () => {
    setIsStreaming(false)
    try {
      await axios.post(`${FLASK_SERVER}/stop_detection`)
      if (imgRef.current) {
        imgRef.current.src = ""
      }
    } catch (err) {
      // console.error('Error stopping detection:', err);
      if (socketRef.current) {
        socketRef.current.emit("force_disconnect")
      }
    }
  }, [FLASK_SERVER])

  // Setup WebSocket connection
  useEffect(() => {
    // Initialize socket connection
    socketRef.current = io(FLASK_SERVER)

    // Socket event listeners
    socketRef.current.on("connect", () => {
      console.log("Connected to WebSocket server")
      setError(null)
    })

    socketRef.current.on("connect_error", (err) => {
      console.error("Connection error:", err)
      setError("Connection to server failed")
      setIsStreaming(false)
    })

    socketRef.current.on("gesture_update", (data) => {
      // Update the image if frame data is available
      if (data.frame && imgRef.current) {
        imgRef.current.src = `data:image/jpeg;base64,${data.frame}`
      }

      // Update gesture data
      setGestureData({
        gesture: data.gesture || "No Gesture Detected",
        confidence: data.confidence || 0.0,
        handedness: data.handedness || "Unknown",
        hand_count: data.hand_count || 0,
        fps: data.fps || 0,
        current_fps: data.current_fps || data.fps || 0,
      })

      setIsStreaming(true)

      // Update button states if provided
      if (data.button_states && Array.isArray(data.button_states)) {
        setButtonStates({
          button1: data.button_states[0] === "ON",
          button2: data.button_states[1] === "ON",
          button3: data.button_states[2] === "ON",
        })
      }
    })

    // socketRef.current.on('camera_error', (data) => {
    //   console.error('Camera error:', data.message);
    //   setError(data.message);
    //   setIsStreaming(false);
    // });

    socketRef.current.on("button_update", (data) => {
      const { button, state } = data
      setButtonStates((prev) => ({
        ...prev,
        [`button${button}`]: state === "ON",
      }))
    })

    socketRef.current.on("system_status", (status) => {
      console.log("System status:", status)
      setIsStreaming(status === "active")
    })

    socketRef.current.on("mode_change", (data) => {
      console.log("Mode changed:", data.mode)
      setCurrentMode(data.mode)
    })

    socketRef.current.on("disconnect", () => {
      console.log("Disconnected from WebSocket server")
      setIsStreaming(false)
    })

    // Cleanup on component unmount
    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect()
        socketRef.current.off("connect")
        socketRef.current.off("connect_error")
        // socketRef.current.off('camera_error');
        socketRef.current.off("gesture_update")
        socketRef.current.off("button_update")
        socketRef.current.off("system_status")
        socketRef.current.off("mode_change")
        socketRef.current.off("disconnect")
      }
    }
  }, [FLASK_SERVER])

  // Handle button toggle events
  useEffect(() => {
    if (!socketRef.current) return

    const handleButtonToggle = (data) => {
      setButtonStates((prev) => ({
        ...prev,
        [`button${data.button}`]: data.state === "ON",
      }))

      // Add haptic feedback for mobile devices
      if (typeof window.navigator.vibrate === "function") {
        window.navigator.vibrate(50)
      }

      // // Add button-specific actions
      // switch (data.button) {
      //   case 1:
      //     console.log("Voice feedback toggled:", data.state)
      //     // Add any voice-specific logic here
      //     break
      //   case 2:
      //     console.log("Gesture mode toggled:", data.state)
      //     // Add mode change logic here
      //     break
      //   case 3:
      //     console.log("Emergency stop activated")
      //     stopDetection()
      //     break
      //   default:
      //     break
      // }
    }

    socketRef.current.on("button_toggle", handleButtonToggle)

    return () => {
      if (socketRef.current) {
        socketRef.current.off("button_toggle", handleButtonToggle)
      }
    }
  }, [stopDetection]) // Added stopDetection as dependency

  // Function to start gesture detection
  const startDetection = useCallback(async () => {
    try {
      console.log("Starting detection...")
      setError(null)
      const response = await axios.post(`${FLASK_SERVER}/start_detection`, {
        settings: {
          sensitivity: settings.sensitivity,
          resolution: settings.resolution,
        },
      })
      console.log("Start detection response:", response.data)
      if (response.data.status === "Detection Started") {
        console.log("Detection started successfully")
        setIsStreaming(true)
      }
    } catch (err) {
      console.error("Error starting detection:", err)
      setError("Failed to connect to the server. Please check if the backend is running.")
    }
  }, [FLASK_SERVER, settings.sensitivity, settings.resolution])

  // Add this useCallback for buttonStates setter to prevent unnecessary re-renders
  // const updateButtonStates = useCallback((newStates) => {
  //   setButtonStates((prev) => ({
  //     ...prev,
  //     ...newStates,
  //   }))
  // }, [])

  // // Emergency stop function
  // const emergencyStop = useCallback(() => {
  //   setButtonStates({
  //     button1: false,
  //     button2: false,
  //     button3: false
  //   });
  //   stopDetection();
  //   if (socketRef.current) {
  //     socketRef.current.emit('emergency_stop');
  //   }
  // }, [stopDetection]);

  // Update system settings
  const updateSettings = (newSettings) => {
    setSettings(newSettings)

    // If currently streaming, apply new settings immediately
    if (isStreaming) {
      try {
        axios.post(`${FLASK_SERVER}/update_settings`, {
          settings: {
            sensitivity: newSettings.sensitivity,
            resolution: newSettings.resolution,
          },
        })
      } catch (err) {
        console.error("Error updating settings:", err)
      }
    }
  }

  // Check screen size for responsive design
  useEffect(() => {
    const checkScreenSize = () => {
      const width = window.innerWidth
      setScreenSize({
        isMobile: width < 480,
        isTablet: width >= 480 && width < 992,
        isDesktop: width >= 992
      })
    }

    checkScreenSize()
    window.addEventListener("resize", checkScreenSize)

    return () => window.removeEventListener("resize", checkScreenSize)
  }, [])

  return (
    <AppContext.Provider value={{ currentMode, setCurrentMode }}>
      <ChakraProvider>
        <style>{globalStyles}</style>
        <Box bg={bgColor} minH="100vh">
        {/* Mobile Header with Menu Toggle */}
        {(screenSize.isMobile || screenSize.isTablet) && (
          <Flex as="header" bg={headerBg} p="4" align="center" borderBottom="1px" borderBottomColor={borderColor}>
            <IconButton
              icon={<Icons.MenuIcon />}
              aria-label="Menu"
              variant="ghost"
              onClick={() => setSidebarOpen(true)}
              mr="2"
            />
            <Heading size="md">GestureApp</Heading>
            <Spacer />
            <DarkModeToggle />
          </Flex>
        )}

        {/* Main Content with Sidebar */}
        <Flex gap="0">
          <Sidebar isOpen={(screenSize.isMobile || screenSize.isTablet) ? isSidebarOpen : true} onClose={() => setSidebarOpen(false)} />

          {/* Main Content Area */}
          <Box flex="1" p="2">
            <Container maxW="container.xl" p="0" ml="0">
              <Grid templateColumns={{ base: "1fr", md: "2.5fr 1fr" }} gap="2">
                {/* Left Column */}
                <GridItem>
                  <VStack spacing="3" align="stretch">
                    {/* Top toolbar */}
                    <Flex
                      justify="space-between"
                      align="center"
                      bg={headerBg}
                      p="4"
                      borderRadius="lg"
                      borderWidth="1px"
                      borderColor={borderColor}
                    >
                      <Heading size="md">Gesture Detection</Heading>
                      <HStack>
                        <Tooltip label="Open Settings">
                          <IconButton
                            icon={<Icons.CogIcon />}
                            aria-label="Settings"
                            onClick={onSettingsOpen}
                            variant="ghost"
                          />
                        </Tooltip>
                        <HStack>
                          <Button
                            leftIcon={isStreaming ? <Icons.PauseIcon /> : <Icons.PlayIcon />}
                            colorScheme={isStreaming ? "red" : "green"}
                            onClick={isStreaming ? stopDetection : startDetection}
                          >
                            {isStreaming ? "Stop Detection" : "Start Detection"}
                          </Button>
                          <Button
                            colorScheme={currentMode === 'home_automation' ? "purple" : "blue"}
                            onClick={() => {
                              const newMode = currentMode === 'home_automation' ? 'general_recognition' : 'home_automation';
                              axios.post(`${FLASK_SERVER}/set_mode`, { mode: newMode })
                                .then(response => {
                                  console.log('Mode switched:', response.data);
                                })
                                .catch(err => {
                                  console.error('Error switching mode:', err);
                                });
                            }}
                          >
                            {currentMode === 'home_automation' ? "Switch to General Mode" : "Switch to Home Automation"}
                          </Button>
                        </HStack>
                      </HStack>
                    </Flex>

                    {/* Camera feed and controls */}
                    <Box
                      bg={headerBg}
                      p="4"
                      borderRadius="lg"
                      borderWidth="1px"
                      borderColor={borderColor}
                      height={{ base: "auto", md: "500px" }}
                    >
                      <CameraFeed isStreaming={isStreaming} error={error} imgRef={imgRef} />
                    </Box>

                    {/* Gesture Library Section */}
                    <Box bg={headerBg} p="4" borderRadius="lg" borderWidth="1px" borderColor={borderColor}>
                      <Flex justify="space-between" align="center" mb="4">
                        <Heading size="md">Gesture Library</Heading>
                      </Flex>

                      <Grid templateColumns={{ base: "1fr", sm: "1fr 1fr", lg: "repeat(3, 1fr)" }} gap="4">
                        <GestureCard
                          title="Thumbs Up"
                          description="A simple thumbs up gesture for positive feedback or approval."
                          image="thumsup.jpeg"
                        />
                        <GestureCard
                          title="Open Hand"
                          description="An open palm hand gesture for stopping or greeting."
                          image="open.jpeg"
                        />
                        <GestureCard
                          title="Victory"
                          description="A V-shape with index and middle fingers for victory or peace."
                          image="peace.jpeg"
                        />
                      </Grid>
                    </Box>
                  </VStack>
                </GridItem>

                {/* Right Column */}
                <GridItem>
                  <VStack spacing="3" align="stretch">
                    {/* Live Data Display */}
                    <Box bg={headerBg} p="0" borderRadius="lg" borderWidth="1px" borderColor={borderColor}>
                      <GestureDataDisplay gestureData={gestureData} buttonStates={buttonStates} />
                    </Box>

                    {/* Instructions Card removed - now in sidebar */}
                  </VStack>
                </GridItem>
              </Grid>
            </Container>
          </Box>
        </Flex>

        {/* Settings Modal */}
        <SettingsModal
          isOpen={isSettingsOpen}
          onClose={onSettingsClose}
          settings={settings}
          updateSettings={updateSettings}
        />
      </Box>
    </ChakraProvider>
    </AppContext.Provider>
  )
}

export default App



