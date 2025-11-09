import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any

import requests
from canvasapi import Canvas
from canvasapi.exceptions import ResourceDoesNotExist, Unauthorized
from colorama import Fore, Style, init
from InquirerPy import prompt
from canvasapi.course import Course

CANVAS_TOKEN: str = None
API_URL: str = None
canvas: Canvas = None 

MAX_THREADS: int = 2 

def sanitize_filename(name):
    return re.sub(r"[^\w\-_\. ]", "_", name)


def download_file(file_url, file_name, folder_dir):
    if not file_url.startswith("http"):
        print(Fore.RED + f"Invalid URL: {file_url}")
        return

    dest_path = os.path.join(folder_dir, sanitize_filename(file_name))
    try:
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(Fore.GREEN + f"Successfully downloaded: {dest_path}")
    except Exception as e:
        print(Fore.RED + f"Failed to download {file_url}: {e}")


def process_files(files, folder_dir):
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor: 
        futures = []
        for file in files:
            if not file.url:
                print(Fore.RED + f"Skipping file with no URL: {file}")
                continue
            future = executor.submit(
                download_file, file.url, file.display_name, folder_dir
            )
            futures.append(future)

        for future in futures:
            future.result()

def download_folder_contents(folder, folder_dir):
    try:
        files = folder.get_files()
        process_files(files, folder_dir)
        subfolders = folder.get_folders()
        for subfolder in subfolders:
            subfolder_dir = os.path.join(folder_dir, sanitize_filename(subfolder.name))
            os.makedirs(subfolder_dir, exist_ok=True)
            download_folder_contents(subfolder, subfolder_dir)
    except Unauthorized as e:
        print(Fore.RED + f"Unauthorized access to folder {folder.id}: {e}")


def download_course_files(course_id):
    try:
        course = canvas.get_course(course_id)
        print(Fore.YELLOW + f"Processing course: {course.name}")

        course_name = sanitize_filename(course.name)
        course_dir = os.path.join("canvas_downloads", course_name)

        if os.path.exists(course_dir):
            print(
                Fore.CYAN
                + f"Skipping course {course.name} because it already has a folder."
            )
            return

        os.makedirs(course_dir, exist_ok=True)

        try:
            folders = course.get_folders()
            root_folder = next(
                (f for f in folders if f.full_name == "course files"), None
            )
            if root_folder:
                download_folder_contents(root_folder, course_dir)
        except Unauthorized as e:
            print(Fore.RED + f"Unauthorized access in course {course_id}: {e}")
        except Exception as e:
            print(Fore.RED + f"Error processing files in course {course_id}: {e}")

        try:
            modules = course.get_modules()
            for module in modules:
                module_name = sanitize_filename(module.name)
                module_dir = os.path.join(course_dir, module_name)
                os.makedirs(module_dir, exist_ok=True)
                try:
                    module_items = module.get_module_items()
                    for item in module_items:
                        if item.type == "File":
                            try:
                                file = canvas.get_file(item.content_id)
                                if file and file.url:
                                    process_files([file], module_dir)
                                else:
                                    print(
                                        Fore.RED
                                        + f"No URL for file in module item {item.id} in course {course_id}"
                                    )
                            except ResourceDoesNotExist:
                                print(
                                    Fore.RED
                                    + f"File not found for module item {item.id} in course {course_id}"
                                )
                except Unauthorized as e:
                    print(
                        Fore.RED
                        + f"Unauthorized access to module items in module {module.id} in course {course_id}: {e}"
                    )
                except Exception as e:
                    print(
                        Fore.RED
                        + f"Error processing module items in module {module.id} in course {course_id}: {e}"
                    )
        except Unauthorized as e:
            print(
                Fore.RED + f"Unauthorized access to modules in course {course_id}: {e}"
            )
        except Exception as e:
            print(Fore.RED + f"Error processing modules in course {course_id}: {e}")

    except Unauthorized as e:
        print(Fore.RED + f"Unauthorized access to course {course_id}: {e}")
    except ResourceDoesNotExist as e:
        print(Fore.RED + f"Course {course_id} does not exist: {e}")
    except Exception as e:
        print(Fore.RED + f"Error processing course {course_id}: {e}")


def get_credentials_interactively():
    questions = [
        {
            "type": "input",
            "name": "api_url",
            "message": "Enter your Canvas base URL (e.g., https://[institution].instructure.com/):",
            "validate": lambda val: True if val.startswith("http") else "URL must start with http:// or https://",
        },
        {
            "type": "password",
            "name": "token",
            "message": "Enter your Canvas Personal Access Token:",
            "validate": lambda val: True if val else "Token cannot be empty.",
        },
    ]
    return prompt(questions)


def select_courses_interactively(canvas_courses: List[Course]) -> List[int]:
    choices = []
    for course in canvas_courses:
        label = f"{course.name} (ID: {course.id})"
        choices.append({"name": label, "value": course.id})

    questions = [
        {
            "type": "checkbox",
            "name": "selected_courses",
            "message": "Select the courses you want to download:",
            "choices": choices,
            "default": [],

            "long_instruction": "Use arrows (↑↓) to navigate, SPACE to select/deselect, Ctrl+A to select All, Ctrl+R to select None , and ENTER to confirm.",
            "cycle": True
        }
    ]
    
    try:
        result = prompt(questions)
        return result.get("selected_courses", [])
    except Exception:
        print(Fore.RED + "\nSelection cancelled or error occurred in the interactive interface.")
        return []

def get_thread_count_interactively():
    questions = [
        {
            "type": "input",
            "name": "max_threads",
            "message": "Enter the maximum number of simultaneous downloads (threads):",
            "default": "2",
            "validate": lambda val: True if val.isdigit() and int(val) > 0 else "Please enter a positive integer.",
        }
    ]
    result = prompt(questions)
    return int(result.get('max_threads', 2))

if __name__ == "__main__":
    init(autoreset=True)

    try:
        # 1. GET CREDENTIALS INTERACTIVELY
        credentials = get_credentials_interactively()
        
        API_URL = credentials.get('api_url')
        CANVAS_TOKEN = credentials.get('token')
        
        if not API_URL or not CANVAS_TOKEN:
            print(Fore.RED + "Incomplete credentials. Exiting.")
            exit()
            
        # 2. GET THREAD COUNT INTERACTIVELY
        MAX_THREADS = get_thread_count_interactively()
        
        # 3. INITIALIZE CANVAS CONNECTION
        try:
            canvas = Canvas(API_URL, CANVAS_TOKEN)
        except Exception as e:
            print(Fore.RED + f"Error initializing Canvas connection: {e}")
            exit()

        if not os.path.exists("canvas_downloads"):
            os.makedirs("canvas_downloads")
            
        # 4. GET COURSE DATA
        try:
            print(Fore.YELLOW + "Connecting to Canvas...")
            all_courses = list(canvas.get_courses(enrollment_state=["active", "completed"]))
        except Exception as e:
            print(Fore.RED + f"Error fetching course list: {e}")
            exit()

        # 5. INTERACTIVE COURSE SELECTION (TUI)
        course_ids = select_courses_interactively(all_courses)
        
        # 6. EXECUTION
        course_ids.reverse()

        if not course_ids:
             print(Fore.RED + "\n No courses selected for download. Exiting... Bye!")
        else:
            print(Style.BRIGHT + Fore.YELLOW + f"\n--- STARTING DOWNLOAD OF {len(course_ids)} SELECTED COURSE(S) with {MAX_THREADS} threads ---")
            for course_id in course_ids:
                download_course_files(course_id)

    except KeyboardInterrupt:
        print(Fore.CYAN + Style.BRIGHT + "\n\n Script interrupted by user. Bye-bye!")
        exit()