// import { extendTheme } from "@chakra-ui/react"

// const config = {
//   initialColorMode: "light",
//   useSystemColorMode: false,
// }

// export const theme = extendTheme({
//   config,
//   fonts: {
//     heading: "Poppins, sans-serif",
//     body: "Inter, sans-serif",
//   },
//   colors: {
//     brand: {
//       50: "#e3f2fd",
//       100: "#bbdefb",
//       500: "#2196f3",
//       600: "#1e88e5",
//       700: "#1976d2",
//       900: "#0d47a1",
//     },
//   },
// })


import { extendTheme } from "@chakra-ui/react";

const config = {
  initialColorMode: "light",
  useSystemColorMode: false,
};

export const theme = extendTheme({
  config,
  fonts: {
    heading: "Poppins, sans-serif",
    body: "Inter, sans-serif",
  },
  colors: {
    brand: {
      50: "#e3f2fd",
      100: "#bbdefb",
      500: "#2196f3",
      600: "#1e88e5",
      700: "#1976d2",
      900: "#0d47a1",
    },
  },
  components: {
    Button: {
      variants: {
        virtual: {
          bg: "blackAlpha.400",
          _hover: {
            bg: "blackAlpha.500",
            transform: "scale(1.05)",
          },
          _active: {
            bg: "blackAlpha.600",
          },
        },
      },
    },
  },
});
