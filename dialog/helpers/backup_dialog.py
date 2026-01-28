import paho.mqtt.client as mqtt
import time
import os
import asyncio
import random
import uuid
import json
from termcolor import colored 
from queue import Queue
from datetime import datetime, timezone


#BROKER = "mqtt01.carma"
BROKER = os.getenv('MQTT_BROKER', 'mosquitto')
#BROKER = os.getenv('MQTT_BROKER', 'localhost')
PORT = int(os.getenv('MQTT_PORT', 1883))
USERNAME = os.getenv('USERNAME', 'inesc')
PASSWORD = os.getenv('PASSWORD', 'inesc')

class BackupInteraction:

    def __init__(self,robotname,language='en'):

        self.alternative_questions = {} #Change this with the questions and answers of the json file

        self.victim_situation = { #Change this so it makes sense with the object of the json file
            "injuries": None, #0 #1
            "people_in_surroundings": None, #6
            "robot_action": None, #7 #8 
            "can_walk": None, #4
            "breathing": None, #2
            "consciousness": None, #skip this one if interaction is not at the beggining
            "stuck_trapped": None, #3
            "immediate_danger": None, #5
            "priority": "Yellow",
        }

        self.question_to_field = {
            "consciousness": 0,
            "injuries": 1,
            "breathing": 2,
            "stuck_trapped": 3,
            "immediate_danger": 5,
            "can_walk": 4,
            "people_in_surroundings": 6,
            "robot_action": [7,8],
        }

        self.occupied_nodes = []
        self.language=language
        self.robotname=robotname

        # Queue to receive STT responses from speech module
        self.stt_queue = Queue()

        self.dialog_client = mqtt.Client(userdata=self.robotname)
        self.dialog_client.will_set("victim/dialogmanager2/lwt", "offline")
        self.dialog_client.on_connect = self.on_connect
        self.dialog_client.on_message = self.on_stt_message
        self.dialog_client.username_pw_set(USERNAME, PASSWORD)
        self.dialog_client.connect(BROKER, PORT)
        self.dialog_client.loop_start()
        self.in_background = True
        self.first_message = True
        self.victim_id = None

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(colored("✅ Connected to broker","yellow"))
            self.dialog_client.subscribe(f"victim/text2speech2text/stt-{userdata}")
            self.dialog_client.subscribe("victim/text2speech2text/lwt")         
            self.dialog_client.publish("victim/dialogmanager2/lwt", "online")
        else:
                print(colored("❌ Bad connection. Returned code=","yellow"), rc)    


    # -----------------------
    # MQTT Callbacks
    # -----------------------
    def on_stt_message(self,client, userdata, msg):
        if msg.payload.decode() != "":
            msg_topic = msg.topic
            if msg_topic == "victim/text2speech2text/lwt":
                print(colored(f"Text2speech2Text status update: {msg.payload.decode()}","yellow"))         
            elif not self.in_background:    
                response = json.loads(msg.payload.decode())
                data = response["data"]
                new_msg = data["message"]
                if self.victim_id is None:
                    self.victim_id = response["data"]["victim_id"]

                print(colored(f"\nVICTIM: {new_msg}","yellow"))
                self.stt_queue.put(data)

                if self.first_message:
                    self.first_message = False
                    self.dialog_client.publish(f"victim/text2speech2text/stt-{userdata}",payload="", qos=1, retain=True) 

    # -----------------------
    # Helper Functions
    # -----------------------
    def speak(self,text,last = False):
        print(colored(f"\nUGV: {text}","yellow"))

        json_msg = {
            "header":{
                "sender": "DialogManager",
                "msg_id": str(uuid.uuid4()),
                "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "msg_type": "UGV's message",
                "msg_content": f"victim/text2speech2text/tts-{self.robotname}"},
            "data":{
                "message": text,
                "victim_id": self.victim_id,
                "last_message": last,
            }
        }

        json_msg = json.dumps(json_msg)
        self.dialog_client.publish(f"victim/text2speech2text/tts-{self.robotname}", str(json_msg))

    def listen(self,timeout=30):
        """Wait for STT response from the speech module."""
        try:
            data = self.stt_queue.get(timeout=timeout)
            return data["message"]
        except KeyboardInterrupt:
            print(colored("\n[Dialog Manager] Interrupted by user. Exiting...","yellow"))
            raise  
        except:
            return "No response"

    def analyze_response(self,response): #use the answers of the json file, so it works with different languages
        response = response.lower()
        if self.language == "en":
            if "no" in response:
                return "negative"
            if "yes" in response or "i can" in response:
                return "positive"
            return "unknown"
        elif self.language == "fr":
            if "non" in response:
                return "negative"
            if "oui" in response or "je peux" in response:
                return "positive"
            return "unknown"
        elif self.language == "es":
            if "no" in response:
                return "negative"
            if "sí" in response or "si" in response or "puedo" in response:
                return "positive"
            return "unknown"
    
    
    def identify_selected_nodes(self):
        print(colored("identifying nodes","green"))
        for field in self.victim_situation:
            if type(self.victim_situation[field]) == str and field != "priority" and field != "consciousness":
                if type(self.question_to_field[field]) == int:
                    self.occupied_nodes.append(self.question_to_field[field])
                else:
                    self.occupied_nodes.append(self.question_to_field[field][0])
                    self.occupied_nodes.append(self.question_to_field[field][1])


    def select_node(self,last_node, last_answer, mobility):
        next_node = last_node + 1

        print(colored(f"This is the node that is going to be searched now: {next_node}","green"))
        while next_node in self.occupied_nodes:
            next_node += 1
            print(colored(f"This is the node that is going to be searched now: {next_node}","green"))


        if last_node == 0 and last_answer == "negative":
            return 2, mobility
        if last_node == 3 and last_answer == "positive":
            mobility = False
            return 5, mobility
        if last_node == 4 and last_answer == "positive":
            mobility = True    
        if last_node == 6:
            return (8 if mobility else 7), mobility
        return next_node, mobility
    
    def send_status_to_c2(self):
        data = {}
        data["victim_id"] = self.victim_id

        for key in self.victim_situation:
            if self.victim_situation[key] != None:
                data[key] = self.victim_situation[key]
        
        
        status_report_msg = {
            "header": {
                "sender": "dialogManager",
                "msg_id": str(uuid.uuid4()),
                "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "msg_type": "Creation",
                "msg_content": "victim/dialogmanager/report"},
            "data": data
            }
        
    
        status_report_msg = json.dumps(status_report_msg)
        self.dialog_client.publish("victim/dialogmanager/report", str(status_report_msg))

    def interact(self,node):
        if node == 7:
            question = self.alternative_questions[node][0]
        elif node == 8:
            question = self.alternative_questions[node][1]
        else:
            question = self.alternative_questions[node]
        repeat = False
        while True:
            if not repeat:
                if node < 7:
                    #print(colored(question,"yellow"))
                    self.speak(question)
                else:
                    #print(colored(question,"yellow"))
                    self.speak(question,last=True)
                    status = "positive"
                    break    
            response = self.listen(timeout=40)
            status = self.analyze_response(response)

            if response != "No response":
                break
            repeat = True
            #print(colored("I didn't catch that. Could you please repeat?","yellow"))
            self.speak("I didn't catch that. Could you please repeat?")

        # Update this part based on the new questions
        if node == 1:
            self.victim_situation["injuries"] = response
            self.victim_situation["consciousness"] = "Conscious"
        elif node == 2:
            self.victim_situation["breathing"] = ("Trouble Breathing" if status == "positive" else "No trouble")
        elif node == 3:
            if status == "positive":
                self.victim_situation["stuck_trapped"] = "Possibly stuck"
                self.victim_situation["robot_action"] = "Wait for responder"
                self.victim_situation["can_walk"] = "Cannot walk"
            else:
                self.victim_situation["stuck_trapped"] = "Possibly not stuck"
        elif node == 4:
            if status == "positive":
                self.victim_situation["can_walk"] = "Can walk"
                self.victim_situation["robot_action"] = "Guide victim"
            else:
                self.victim_situation["can_walk"] = "Cannot walk"
                self.victim_situation["robot_action"] = "Wait for responder"
        elif node == 5:
            self.victim_situation["people_in_surroundings"] = ("Others present" if status == "positive" else "None nearby")
        elif node == 6:
            self.victim_situation["immediate_danger"] = ("Danger nearby" if status == "positive" else "Not clear")

        self.send_status_to_c2()    
        
        return status

    def read_question_file(self):
        # Check if the file exists before attempting to open it
        file_path = f"../backup_questions/backup_{self.language}.json"
        if not os.path.exists(file_path):
            print(f"[ERROR] File not found: {file_path}")
            return

        try:
            # 1. Opening and reading the file
            # Using 'with open(...)' handles closing the file automatically, 
            # so you don't need 'json_data.close()'
            with open(file_path, 'r') as json_file:
                # 2. Loading the JSON data
                data = json.load(json_file) 

            
            # 3. Extracting the "questions" data
            questions = data["questions"]

            # 4. Processing the questions
            for item in questions:
                # Note: Assuming self.victim_situation and self.question_to_field 
                # are properly initialized instance attributes
                if item not in self.victim_situation:
                    # If a key is missing, this is an issue with the file content/format
                    print(f"[ERROR] Question key '{item}' not found in 'self.victim_situation'. JSON format error.")
                    return
                
                node = self.question_to_field[item]
                if type(node) == int:
                    self.alternative_questions[node] = questions[item]
                else:
                    self.alternative_questions[node[0]] = questions[item]
                    self.alternative_questions[node[1]] = questions[item]
                    
            print(self.alternative_questions)
        # Handle common expected errors specifically:
        # Error: File exists but cannot be opened (e.g., permissions)
        except IOError as e: 
            print(f"[ERROR] I/O Error when opening file: {e}") 
            
        # Error: File exists but is not valid JSON
        except json.JSONDecodeError as e: 
            print(f"[ERROR] JSON Decoding Error: The file content is not valid JSON. Details: {e}")

        # Error: The loaded JSON object is missing the 'questions' key
        except KeyError as e: 
            print(f"[ERROR] KeyError: Missing required JSON key {e} (Expected 'questions'). JSON format error.") 

        # Handle any other unexpected exceptions (e.g., issues with self.question_to_field lookup)
        except Exception as e:
            print(f"[ERROR] An unexpected error occurred: {type(e).__name__}: {e}")   

    async def on_standby(self,report_queue):
        #Receive status report updates from the main dialog manager and updates victim_situation
        print(colored("I'm on standby!","yellow"))
        
        while(True):
            assessment = await report_queue.get()
            if "info" in assessment:
                if assessment["info"] == "fail_at_start":
                    print(colored(f"The dialog manager failed before the first response","yellow"))
                    self.in_background = False
                    return None
                else:
                    print(colored(f"The dialog manager failed, this is the last response: {assessment['data']}","yellow"))
                    self.victim_situation["consciousness"] = "Conscious"
                    self.in_background = False
                    self.first_message = False
                    print(colored(self.victim_situation,"yellow"))
                    self.identify_selected_nodes()
                    print(colored(self.occupied_nodes,"green"))
                    print(colored(self.question_to_field,"green"))

                    return assessment['data']
            else:
                print(colored(f"assement received: {assessment}","yellow"))    
                if assessment != {}:
                    for item in assessment:
                        self.victim_situation[item] = assessment[item]

    def wait_for_first_message(self):
        data = self.stt_queue.get()                     

    async def interaction_tree(self, start_node=-1, last_answer="positive",queue=None):
        self.read_question_file()

        last_message = await self.on_standby(queue)
        if last_message is not None:
            last_answer = self.analyze_response(last_message)
            print(colored(f"last Answer: {last_message}, this message is {last_answer}","green"))
        mobility = None
        node = start_node
        if self.first_message:
            self.wait_for_first_message()

        while True:
            node, mobility = self.select_node(node, last_answer, mobility)
            last_answer = self.interact(node)
            if node == 7 or node == 8:
                break

        return self.victim_id    

