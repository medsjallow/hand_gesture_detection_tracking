int LIGHT = D1;  // Pin connected to the LIGHT
int FAN = D2;    // Pin connected to the FAN
int PUMP = D3;
int command=7;

void setup() {
  Serial.begin(9600);  // Initialize serial communication at 9600 baud rate
  pinMode(LIGHT, OUTPUT);  // Set LIGHT pin as output
  pinMode(FAN, OUTPUT);    // Set FAN pin as output
  pinMode(PUMP, OUTPUT);   // Set PUMP pin as output
  digitalWrite(LIGHT, HIGH);
  digitalWrite(FAN, HIGH);
  digitalWrite(PUMP, HIGH);
}

void loop() {
  if (Serial.available() > 0) {
    int newcomm = Serial.parseInt();
    if (newcomm != 0) {
      command = newcomm;
      //Serial.println(command);
    }
  }
  switch (command) {
    case 1:
      digitalWrite(LIGHT, HIGH);
      Serial.println("LIGHT ON");
      break;
    case 2:
      digitalWrite(LIGHT, LOW);
      Serial.println("LIGHT OFF");
      break;
    case 3:
      digitalWrite(FAN, LOW);
      Serial.println("FAN ON");
      break;
    case 4:
      digitalWrite(FAN, HIGH);
      Serial.println("FAN OFF");
      break;
    case 5:
      digitalWrite(PUMP, LOW);
      Serial.println("PUMP ON");
      break;
    case 6:
      digitalWrite(PUMP, HIGH);
      Serial.println("PUMP OFF");
      break;
    default:
      Serial.println("INVALID COMMAND"); // For safety, in case of unknown command
      break;
  }
}
