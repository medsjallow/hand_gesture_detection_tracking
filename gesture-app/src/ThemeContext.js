"use client"

import { createContext, useContext, useState, useEffect } from "react"

// Create a context for theme
export const ThemeContext = createContext(null)

export const ThemeProvider = ({ children }) => {
  // Check if the user has a preference stored in localStorage
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const savedMode = localStorage.getItem("darkMode")
    return savedMode ? JSON.parse(savedMode) : false
  })

  // Update localStorage when isDarkMode changes
  useEffect(() => {
    localStorage.setItem("darkMode", JSON.stringify(isDarkMode))
  }, [isDarkMode])

  // Toggle dark mode
  const toggleDarkMode = () => {
    setIsDarkMode(!isDarkMode)
  }

  return <ThemeContext.Provider value={{ isDarkMode, toggleDarkMode }}>{children}</ThemeContext.Provider>
}

// Custom hook for using the theme
export const useTheme = () => useContext(ThemeContext)





// import React, { createContext, useContext, useState, useEffect } from 'react';

// // Create a context for theme
// export const ThemeContext = createContext();

// export const ThemeProvider = ({ children }) => {
//   // Check if the user has a preference stored in localStorage
//   const [isDarkMode, setIsDarkMode] = useState(() => {
//     const savedMode = localStorage.getItem('darkMode');
//     return savedMode ? JSON.parse(savedMode) : false;
//   });

//   // Update localStorage when isDarkMode changes
//   useEffect(() => {
//     localStorage.setItem('darkMode', JSON.stringify(isDarkMode));
//   }, [isDarkMode]);

//   // Toggle dark mode
//   const toggleDarkMode = () => {
//     setIsDarkMode(!isDarkMode);
//   };

//   return (
//     <ThemeContext.Provider value={{ isDarkMode, toggleDarkMode }}>
//       {children}
//     </ThemeContext.Provider>
//   );
// };

// // Custom hook for using the theme
// export const useTheme = () => useContext(ThemeContext);
