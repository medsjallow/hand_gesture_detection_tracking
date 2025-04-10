import React from 'react';
import { Box, Heading, Stack, Badge, Text, Divider, HStack, Icon } from '@chakra-ui/react';
import { FiToggleLeft, FiToggleRight } from 'react-icons/fi';

const ActiveControls = ({ buttonStates }) => {
  return (
    <Box 
      borderWidth="1px" 
      borderRadius="lg" 
      p={4}
      boxShadow="sm"
      bg="white"
      _dark={{ bg: "gray.800" }}
    >
      <Heading size="md" mb={3}>Active Controls</Heading>
      <Divider mb={3} />
      
      <Stack spacing={3}>
        {[1, 2, 3].map((btnNum) => (
          <HStack key={btnNum} justify="space-between">
            <Text fontWeight="medium">Button {btnNum}</Text>
            <HStack>
              <Badge 
                colorScheme={buttonStates[`button${btnNum}`] ? "green" : "gray"}
                variant="subtle"
                px={2}
                py={1}
                borderRadius="full"
              >
                {buttonStates[`button${btnNum}`] ? "Active" : "Inactive"}
              </Badge>
              <Icon 
                as={buttonStates[`button${btnNum}`] ? FiToggleRight : FiToggleLeft} 
                color={buttonStates[`button${btnNum}`] ? "green.500" : "gray.500"}
                boxSize={5}
              />
            </HStack>
          </HStack>
        ))}
      </Stack>
    </Box>
  );
};

export default ActiveControls;