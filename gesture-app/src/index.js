import React from "react"
import ReactDOM from "react-dom/client"
import App from "./App"
import { ChakraProvider, ColorModeScript } from "@chakra-ui/react"
import { ThemeProvider } from "./ThemeContext"
import { theme } from "./theme"

const root = ReactDOM.createRoot(document.getElementById("root"))
root.render(
  <React.StrictMode>
    <ChakraProvider theme={theme}>
      <ColorModeScript initialColorMode={theme.config.initialColorMode} />
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </ChakraProvider>
  </React.StrictMode>,
)


// import React from 'react';
// import ReactDOM from 'react-dom';
// import './index.css';
// import App from './App';
// import reportWebVitals from './reportWebVitals';
// import { ChakraProvider, ColorModeScript } from '@chakra-ui/react';
// import { ThemeProvider } from './ThemeContext';

// // Create a theme object with color mode config
// const theme = {
//   config: {
//     initialColorMode: 'light',
//     useSystemColorMode: false,
//   },
// };

// ReactDOM.render(
//   <React.StrictMode>
//     <ChakraProvider>
//       <ColorModeScript initialColorMode={theme.config.initialColorMode} />
//       <ThemeProvider>
//         <App />
//       </ThemeProvider>
//     </ChakraProvider>
//   </React.StrictMode>,
//   document.getElementById('root')
// );

// // If you want to start measuring performance in your app, pass a function
// // to log results (for example: reportWebVitals(console.log))
// // or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
// reportWebVitals();