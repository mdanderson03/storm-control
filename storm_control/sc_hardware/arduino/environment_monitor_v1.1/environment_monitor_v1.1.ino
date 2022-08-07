// Environment Monitor
// v1.1
// Jeffrey Moffitt
// Started: July 2022
// Updaet: August 2022
// Children's Hospital Boston 2022

// This code draws heavily from examples from Adafruit. Consult the adafruit website on the necessary Adafruit libraries
// This environment monitor was built on a Feather M4, a SHX110 display, and a HTS211 or AHT20 sensor. It should be straightforward 
// to modify for other hardware choices

// Display Headers
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

// Sensor Headers
#include <Adafruit_Sensor.h>
#include <Adafruit_HTS221.h>
#include <Adafruit_AHTX0.h>

// Display definitions
Adafruit_SH1107 display = Adafruit_SH1107(64, 128, &Wire);

// Sensor definitions
Adafruit_HTS221 hts;
Adafruit_AHTX0 aht;

//Define sensor constants
const int NULL_SENSOR = 0;
const int HTS221_SENSOR = 1;
const int AHTX0_SENSOR = 2;
int Sensor_Type = NULL_SENSOR;

// Code definition
String VERSION = "EMonitor_v1.1";

void setup() {

  // Create the display
  display.begin(0x3C, true); // Address 0x3C default

  // Display the splash screen
  display.display();
  delay(1000);

  // Clear the display
  display.clearDisplay();
  display.display();
  display.setRotation(1);

  // Configure the display for error reports
  display.setTextSize(1);
  display.setTextColor(SH110X_WHITE);
  display.setCursor(0,0);

  // Display Software version
  display.println(VERSION);

  // Create the temperature and humidity sensor
  if (Sensor_Type == NULL_SENSOR){
    if (hts.begin_I2C()) {
      display.println("HTS221 FOUND");
      Sensor_Type = HTS221_SENSOR;
      //Configure the device
      hts.setDataRate(HTS221_RATE_1_HZ);
      //Report on configuration
      display.println("HTS211 Sample Rate:");
      hts221_rate_t value;
      value = hts.getDataRate();
      display.print(" ");
      display.println(value);
    }
  }
  if (Sensor_Type == NULL_SENSOR){
    if (aht.begin()){
      display.println("AHTX0 FOUND");
      Sensor_Type = AHTX0_SENSOR;
    }
  }
  if (Sensor_Type == NULL_SENSOR){
    display.println("ERROR! NO SENSOR!");
  }

  display.print("Sensor Type: ");
  display.println(String(Sensor_Type));
  
  display.display();

  // Setup the serial port
  Serial.begin(115200);
  
  // Delay so that the status and configuration can display
  delay(5000);
  display.clearDisplay();
  display.display();
  display.setCursor(0,0);
  display.setTextSize(3);

}

// Define properties of the main loop
int counter = 0; // To set the frequency of measurement // Upgrade to time
String tempToDisplay; // Temperature string
String humidityToDisplay; // Humidity string
String command; // The read command from the serial port
String readCommand = "read"; // The serial command to read the status
String message = ""; // The returned message string

// Main loop
void loop() {

  //Reset the command string and check the serial port for new reads
  command = "";
  if (Serial.available() > 0){
    command = Serial.readStringUntil('\n');
  }

  //If the read command is provided, return the current temperature and humidity strings in a json struct
  if (command == readCommand) {
    Serial.print("{\"temperature\":\"");
    Serial.print(tempToDisplay);
    Serial.print("C\"");
    Serial.print(", ");
    Serial.print("\"humidity\":\"");
    Serial.print(humidityToDisplay);
    Serial.print("%\"");
    Serial.println("}");
  }
  else { //If the system is not responding to a read request, then update the temperature/humidity and display
    //Update temp/humidity and the display
    if (((counter+1) % 100000) == 0){
      // Measure temperature and humidity
      sensors_event_t temp;
      sensors_event_t humidity;

      switch (Sensor_Type){
        case HTS221_SENSOR:
          hts.getEvent(&humidity, &temp);
          break;
        case AHTX0_SENSOR:
          aht.getEvent(&humidity, &temp);
          break;
        case NULL_SENSOR:
          display.println("NO SENSOR"); 
          break;
          
      }

      // Update display
      tempToDisplay = String(temp.temperature,1);
      display.print(tempToDisplay);
      display.println("C");
      humidityToDisplay = String(humidity.relative_humidity,0);
      display.print(humidityToDisplay);
      display.println("%");
      
      display.display();
  
      //Clear display
      display.clearDisplay();
      display.setCursor(0,0);
  
      //Update counters
      counter = 0;  
    }
    counter = counter + 1;
  }
}
