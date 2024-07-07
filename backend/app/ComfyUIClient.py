import requests
import json
import os
import logging
import base64
import time
import uuid
from PIL import Image
from io import BytesIO

# Constants
OUTPUT_FORMAT = 'JPEG'
STATUS_IN_QUEUE = 'IN_QUEUE'
STATUS_IN_PROGRESS = 'IN_PROGRESS'
STATUS_FAILED = 'FAILED'
STATUS_CANCELLED = 'CANCELLED'
STATUS_COMPLETED = 'COMPLETED'
STATUS_TIMED_OUT = 'TIMED_OUT'


class Timer:
    def __init__(self):
        self.start = time.time()

    def restart(self):
        self.start = time.time()

    def get_elapsed_time(self):
        end = time.time()
        return round(end - self.start, 1)


class ComfyUIClient:
    def __init__(self, endpoint_url, api_key, endpoint_id, output_dir=None, input_dir=None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.workflow = None
        self.payload = None
        self.load_image_node_number = 0
        self.seed_node_number = 0
        self.positive_prompt_node_number = 0
        self.negative_prompt_node_number = 0
        self.size_batch_node_number = 0
        self.output_node_number = 0
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _summarize_dict(d, max_length=100):
        def _summarize(value):
            if isinstance(value, dict):
                return {k: _summarize(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [_summarize(v) for v in value]
            elif isinstance(value, str) and len(value) > max_length:
                return f"<str(len={len(value)})>"
            else:
                return value

        return _summarize(d)
    # you need to load_workflow before calling other functions, this will initialize the workflow and payload
    def load_workflow(self, filepath, 
                      seed_node_number, 
                      positive_prompt_node_number, 
                      output_node_number, 
                      negative_prompt_node_number,
                      size_batch_node_number,
                      load_image_node_number=None):
        try:
            with open(filepath, 'r') as f:
                self.workflow = json.load(f)
            self.seed_node_number = seed_node_number
            self.positive_prompt_node_number = positive_prompt_node_number
            self.output_node_number = output_node_number
            self.load_image_node_number = load_image_node_number
            self.negative_prompt_node_number = negative_prompt_node_number
            self.size_batch_node_number = size_batch_node_number
            self.payload = {
                "input": {
                    "workflow": self.workflow
                }
            }
            self.logger.debug("Loaded workflow: %s", self.workflow)
        except Exception as e:
            self.logger.error(f"Error loading workflow from {filepath}: {e}")
            raise

    def update_seed_node(self, seed_value):
        try:
            seed_node = self.workflow.get(str(self.seed_node_number))
            if not seed_node:
                raise ValueError(f"Seed node {self.seed_node_number} not found in the workflow JSON.")
            seed_node["inputs"]["seed"] = seed_value
            self.logger.debug("Updated seed node %s: %s", self.seed_node_number, seed_node)
        except Exception as e:
            self.logger.error(f"Error updating seed node: {e}")
            raise

    def update_positive_prompt(self, prompt_text: str):
        try:
            pos_prompt_node = self.workflow.get(str(self.positive_prompt_node_number))
            if not pos_prompt_node:
                raise ValueError(f"Positive prompt node {self.positive_prompt_node_number} not found in the workflow JSON.")
            pos_prompt_node['inputs']['text'] = str(prompt_text)
            self.logger.debug("Updated positive prompt node %s: %s", self.positive_prompt_node_number, pos_prompt_node)
        except Exception as e:
            self.logger.error(f"Error updating positive prompt node: {e}")
            raise

    def update_negative_prompt(self, prompt_text: str):
        try:
            neg_prompt_node = self.workflow.get(str(self.negative_prompt_node_number))
            if not neg_prompt_node:
                raise ValueError(f"Negative prompt node {self.positive_prompt_node_number} not found in the workflow JSON.")
            neg_prompt_node['inputs']['text'] = str(prompt_text)
            self.logger.debug("Updated negative prompt node %s: %s", self.negative_prompt_node_number, neg_prompt_node)
        except Exception as e:
            self.logger.error(f"Error updating negative prompt node: {e}")
            raise

    def update_output_batch(self, batch_size: int):
        """
        Update the output batch size in the workflow.

        Args:
            batch_size (int): The new batch size for the output.

        Raises:
            ValueError: If the size/batch node is not found in the workflow JSON.
            Exception: For any other errors during the update process.
        """
        try:
            size_batch_node = self.workflow.get(str(self.size_batch_node_number))
            if not size_batch_node:
                raise ValueError(f"Size/batch node {self.size_batch_node_number} not found in the workflow JSON.")
            
            # Update the 'batch_size' input of the node
            size_batch_node['inputs']['batch_size'] = batch_size
            
            self.logger.debug("Updated size/batch node %s: %s", self.size_batch_node_number, size_batch_node)
        except Exception as e:
            self.logger.error(f"Error updating output batch size: {e}")
            raise


    def upload_image(self, local_file_path):
        try:
            with open(local_file_path, 'rb') as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            self.logger.debug("Encoded image to base64")

            image_data = {
                "name": os.path.basename(local_file_path),
                "image": encoded_image
            }

            if "images" not in self.payload["input"]:
                self.payload["input"]["images"] = []
            self.payload["input"]["images"].append(image_data)

            # Update the image file name in the workflow
            load_image_node = self.workflow.get(str(self.load_image_node_number))
            if not load_image_node:
                raise ValueError(f"Load image node {self.load_image_node_number} not found in the workflow JSON.")
            load_image_node['inputs']['image'] = image_data['name']
            self.logger.debug("Updated load image node %s: %s", self.load_image_node_number, load_image_node)

            return encoded_image
        except Exception as e:
            self.logger.error(f"Error uploading image: {e}")
            raise

    def save_result_images(self, resp_json):
        try:
            img_data = resp_json['output']['message']
            img = Image.open(BytesIO(base64.b64decode(img_data)))
            file_extension = 'jpeg' if OUTPUT_FORMAT == 'JPEG' else 'png'
            output_file = os.path.join(self.output_dir, f'{uuid.uuid4()}.{file_extension}')

            with open(output_file, 'wb') as f:
                self.logger.info(f'Saving image: {output_file}')
                img.save(f, format=OUTPUT_FORMAT)
        except Exception as e:
            self.logger.error(f"Error saving result images: {e}")
            raise
    # in web app, we do not save generated media in the backend. so this method is not used.
    def handle_response(self, resp_json, timer=None):
        """
        get the input message schema, save as local file and return the output schema

        input schema from rp_handler:

        {
        "delayTime": 2188,
        "executionTime": 2297,
        "id": "sync-c0cd1eb2-068f-4ecf-a99a-55770fc77391-e1",
        "output": { "message": ["base64encodedimage", "image2", "image3"], "status": "success" },
        "status": "COMPLETED"
        }

        output schema to the main application:

        {"status": "COMPLETED", "saved_images": [saved_image_path1, saved_image_path2, ...]}
        
        """
        try:
            if resp_json['output'] is not None and 'message' in resp_json['output']:
                images = resp_json['output']['message']
                if not isinstance(images, list):
                    images = [images]
                saved_image_paths = []
                for image in images:
                    img = Image.open(BytesIO(base64.b64decode(image)))
                    file_extension = 'jpeg' if img.format == 'JPEG' else 'png'
                    output_file = os.path.join(self.output_dir, f'{uuid.uuid4()}.{file_extension}')
                    with open(output_file, 'wb') as f:
                        self.logger.debug(f'Saving image: {output_file}')
                        img.save(f, format=img.format)
                    saved_image_paths.append(output_file)
                
                if timer is not None:
                    processing_time = timer.get_elapsed_time()
                    self.logger.debug(f'Processing time: {processing_time:.2f} seconds')
                
                return {"status": "COMPLETED", "saved_images": saved_image_paths}
            else:
                self.logger.error("Invalid response format: %s", resp_json)
                raise ValueError("Invalid response format")
        except Exception as e:
            if timer is not None:
                processing_time = timer.get_elapsed_time()
                self.logger.debug(f'Processing time: {processing_time:.2f} seconds')
            self.logger.error("An error occurred: %s", e)
            raise
        
    def post_request(self, run_sync=True):
        """
        post request (sync or async) to the RunPod API

        client request schema (self.payload):
        {
            "input": {
                "workflow": {},
                "images": [
                {
                    "name": "example_image_name.png",
                    "image": "base64_encoded_string"
                }
                ]
            }
        }

        runpod response schema:
        {
            "delayTime": 2188,
            "executionTime": 2297,
            "id": "sync-c0cd1eb2-068f-4ecf-a99a-55770fc77391-e1",
            "output": { "message": ["base64encodedimage", "image2", "image3"], "status": "success" },
            "status": "COMPLETED"
        }
        """
        timer = Timer()
        url_suffix = 'runsync' if run_sync else 'run'
        base_url = f'{self.endpoint_url}/{self.endpoint_id}/{url_suffix}'

        self.logger.debug("Base URL: %s", base_url)
        self.logger.debug("Payload structure: %s", self._summarize_dict(self.payload))
        self.logger.debug("API Key: %s", self.api_key)
        try:
            response = requests.post(
                base_url,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                json=self.payload
            )

            self.logger.info(f'Status code: {response.status_code}')

            if response.status_code == 200:
                resp_json = response.json()
                self.logger.debug("Response JSON: %s", self._summarize_dict(resp_json))
                if 'output' in resp_json:
                    return resp_json
                else:
                    return self.poll_for_completion(resp_json['id'], timer)
            else:
                self.logger.error(f'ERROR: {response.content}')
        except Exception as e:
            self.logger.error(f"Error in post request: {e}")
            raise

    def poll_for_completion(self, request_id, timer):
        base_url = f'{self.endpoint_url}/{self.endpoint_id}'
        request_in_queue = True

        while request_in_queue:
            try:
                response = requests.get(
                    f'{base_url}/status/{request_id}',
                    headers={'Authorization': f'Bearer {self.api_key}'}
                )

                self.logger.info(f'Status code from RunPod status endpoint: {response.status_code}')

                if response.status_code == 200:
                    resp_json = response.json()
                    job_status = resp_json.get('status', STATUS_FAILED)

                    if job_status in [STATUS_IN_QUEUE, STATUS_IN_PROGRESS]:
                        self.logger.info(f'RunPod request {request_id} is {job_status}, sleeping for 5 seconds...')
                        time.sleep(5)
                    elif job_status == STATUS_FAILED:
                        request_in_queue = False
                        self.logger.error(f'RunPod request {request_id} failed')
                        self.logger.error(json.dumps(resp_json, indent=4, default=str))
                    elif job_status == STATUS_COMPLETED:
                        request_in_queue = False
                        self.logger.info(f'RunPod request {request_id} completed')
                        return resp_json
                    elif job_status == STATUS_TIMED_OUT:
                        request_in_queue = False
                        self.logger.error(f'ERROR: RunPod request {request_id} timed out')
                    else:
                        request_in_queue = False
                        self.logger.error(f'ERROR: Invalid status response from RunPod status endpoint')
                        self.logger.error(json.dumps(resp_json, indent=4, default=str))
                else:
                    self.logger.error(f'ERROR: {response.content}')
                    request_in_queue = False
            except Exception as e:
                self.logger.error(f"Error polling for completion: {e}")
                raise

    def queue_prompt_async(self):
        return self.post_request(run_sync=False)

    def queue_prompt_sync(self):
        return self.post_request(run_sync=True)

    def check_job_status(self, job_id):
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        try:
            response = requests.get(f"{self.endpoint_url}/{self.endpoint_id}/status/{job_id}", headers=headers)
            response_data = response.json()
            self.logger.debug("Job status response: %s", response_data)
            return response_data
        except Exception as e:
            self.logger.error(f"Error checking job status: {e}")
            raise
