"""
MQTT Manager Module
Handles MQTT communication between Robot Client and Dialog Manager
"""
import json
import time
import threading
from typing import Callable, Dict, Any, Optional
import paho.mqtt.client as mqtt


class MQTTManager:
    """Manages MQTT communication for the rescue robot system"""
    
    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883, 
                 client_id: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize MQTT manager
        
        Args:
            broker_host: MQTT broker hostname
            broker_port: MQTT broker port
            client_id: Unique client identifier
            username: MQTT username (if authentication required)
            password: MQTT password (if authentication required)
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id or f"rescue_robot_{int(time.time())}"
        self.username = username
        self.password = password
        
        # MQTT client
        self.client = mqtt.Client(client_id=self.client_id, clean_session=True)
        
        # Set up authentication if provided
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Message handlers
        self.message_handlers: Dict[str, Callable] = {}
        
        # Connection status
        self.is_connected = False
        self.connection_lock = threading.Lock()
        
        # Message queue for offline scenarios
        self.message_queue = []
        self.max_queue_size = 100
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            with self.connection_lock:
                self.is_connected = True
            print(f"MQTT: Connected to {self.broker_host}:{self.broker_port}")
            # Process any queued messages
            self._process_message_queue()
        else:
            print(f"MQTT: Connection failed with code {rc}")
            # Set connection status to False on failure
            with self.connection_lock:
                self.is_connected = False
            
            # Provide more detailed error information
            error_messages = {
                1: "Connection refused - unacceptable protocol version",
                2: "Connection refused - identifier rejected", 
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized"
            }
            if rc in error_messages:
                print(f"MQTT: {error_messages[rc]}")
            else:
                print(f"MQTT: Unknown connection error code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        with self.connection_lock:
            self.is_connected = False
        
        if rc != 0:
            print(f"MQTT: Unexpected disconnection (code {rc})")
        else:
            print("MQTT: Disconnected")
    
    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            print(f"MQTT: Received message on {topic}: {payload}")
            
            # Parse JSON payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(f"MQTT: Invalid JSON payload: {payload}")
                return
            
            # Call registered handler
            if topic in self.message_handlers:
                try:
                    self.message_handlers[topic](data)
                except Exception as e:
                    print(f"MQTT: Error in message handler for {topic}: {e}")
            else:
                print(f"MQTT: No handler registered for topic {topic}")
                
        except Exception as e:
            print(f"MQTT: Error processing message: {e}")
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker
        
        Returns:
            True if connection successful
        """
        try:
            print(f"MQTT: Connecting to {self.broker_host}:{self.broker_port}...")
            
            # Reset connection status
            with self.connection_lock:
                self.is_connected = False
            
            # Stop any existing loop
            try:
                self.client.loop_stop()
            except:
                pass
            
            # Start the loop first
            self.client.loop_start()
            
            # Then connect
            result = self.client.connect(self.broker_host, self.broker_port, 60)
            if result != mqtt.MQTT_ERR_SUCCESS:
                print(f"MQTT: Connect call failed with result {result}")
                return False
            
            # Wait for connection callback to be called
            timeout = 10
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self.is_connected:
                print(f"MQTT: Successfully connected to {self.broker_host}:{self.broker_port}")
                return True
            else:
                print(f"MQTT: Connection timeout after {timeout} seconds")
                return False
            
        except Exception as e:
            print(f"MQTT: Connection error: {e}")
            return False
    
    def _recreate_client(self):
        """Recreate the MQTT client for reconnection"""
        try:
            # Stop and cleanup old client
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except:
                pass
            
            # Create new client
            self.client = mqtt.Client(client_id=self.client_id, clean_session=True)
            
            # Set up authentication if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Set up callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            print("MQTT: Client recreated for reconnection")
            
        except Exception as e:
            print(f"MQTT: Error recreating client: {e}")
    
    def reconnect(self) -> bool:
        """
        Reconnect to MQTT broker
        
        Returns:
            True if reconnection successful
        """
        try:
            print("MQTT: Attempting reconnection...")
            
            # Recreate client
            self._recreate_client()
            
            # Try to connect
            return self.connect()
            
        except Exception as e:
            print(f"MQTT: Reconnection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        try:
            if self.is_connected:
                self.client.loop_stop()
                self.client.disconnect()
                with self.connection_lock:
                    self.is_connected = False
                print("MQTT: Disconnected")
        except Exception as e:
            print(f"MQTT: Disconnect error: {e}")
    
    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to a topic with a message handler
        
        Args:
            topic: MQTT topic to subscribe to
            handler: Function to call when message received
        """
        try:
            self.message_handlers[topic] = handler
            if self.is_connected:
                result = self.client.subscribe(topic)
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    print(f"MQTT: Subscribed to {topic}")
                else:
                    print(f"MQTT: Failed to subscribe to {topic}")
            else:
                print(f"MQTT: Not connected, will subscribe when connected")
        except Exception as e:
            print(f"MQTT: Subscribe error: {e}")
    
    def publish(self, topic: str, data: Dict[str, Any], qos: int = 1) -> bool:
        """
        Publish message to a topic
        
        Args:
            topic: MQTT topic to publish to
            data: Data to publish (will be converted to JSON)
            qos: Quality of service level
            
        Returns:
            True if message sent or queued
        """
        try:
            payload = json.dumps(data, ensure_ascii=False)
            
            if self.is_connected:
                result = self.client.publish(topic, payload, qos=qos)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"MQTT: Published to {topic}: {payload}")
                    return True
                else:
                    print(f"MQTT: Failed to publish to {topic}")
                    return False
            else:
                # Queue message for later
                self._queue_message(topic, payload, qos)
                print(f"MQTT: Message queued for {topic} (offline)")
                return True
                
        except Exception as e:
            print(f"MQTT: Publish error: {e}")
            return False
    
    def _queue_message(self, topic: str, payload: str, qos: int):
        """Queue message for later transmission"""
        if len(self.message_queue) >= self.max_queue_size:
            # Remove oldest message
            self.message_queue.pop(0)
        
        self.message_queue.append({
            'topic': topic,
            'payload': payload,
            'qos': qos,
            'timestamp': time.time()
        })
    
    def _process_message_queue(self):
        """Process queued messages when connection is restored"""
        if not self.message_queue:
            return
        
        print(f"MQTT: Processing {len(self.message_queue)} queued messages...")
        
        # Process messages in order
        while self.message_queue:
            msg = self.message_queue[0]
            
            try:
                result = self.client.publish(msg['topic'], msg['payload'], qos=msg['qos'])
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.message_queue.pop(0)
                    print(f"MQTT: Queued message sent to {msg['topic']}")
                else:
                    # Stop processing if we can't send
                    break
            except Exception as e:
                print(f"MQTT: Error processing queued message: {e}")
                break
    
    def is_broker_available(self) -> bool:
        """
        Check if MQTT broker is available
        
        Returns:
            True if broker is reachable
        """
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.broker_host, self.broker_port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current MQTT status
        
        Returns:
            Dictionary with connection status and queue information
        """
        return {
            'connected': self.is_connected,
            'broker_host': self.broker_host,
            'broker_port': self.broker_port,
            'client_id': self.client_id,
            'queued_messages': len(self.message_queue),
            'broker_available': self.is_broker_available()
        }
    
    def cleanup(self):
        """Clean up MQTT resources"""
        try:
            self.disconnect()
        except Exception as e:
            print(f"MQTT: Cleanup error: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()
