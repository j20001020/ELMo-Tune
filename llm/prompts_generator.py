import re
from difflib import Differ
from options_files.ops_options_file import cleanup_options_file
from llm.llm_request import request_llm
from utils.utils import log_update
from dotenv import load_dotenv
import utils.constants as constants

load_dotenv()

def generate_system_content(device_information, rocksdb_version):
    """
    Function to generate the system content with device info and rocksDB version.
    
    Parameters:
        device_information (str): Information about the device.
        
    Returns:
        str: A prompt for configuring RocksDB for enhanced performance.
    """

    content = (
        "You are a RocksDB Expert. "
        "You are being consulted by a company to help improve their RocksDB configuration "
        "by optimizing their options file based on their System information and benchmark output."
        f"Only provide option files for rocksdb version {rocksdb_version}. Also, Direct IO will always be used for both flush and compaction."
        "Additionally, compression type is set to none always."
        "First Explain the reasoning, only change 10 options, then show the option file in original format."
        f"The Device information is: {device_information}"
    )
    return content

def generate_default_user_content(chunk_string, previous_option_files, average_cpu_used=-1.0, average_mem_used=-1.0, test_name="fillrandom"):
    user_contents = []
    for _, benchmark_result, reasoning, _ in previous_option_files[1: -1]:
        benchmark_line = generate_benchmark_info(test_name, benchmark_result, average_cpu_used, average_mem_used)
        user_content = f"The option file changes were:\n```\n{reasoning}\n```\nThe benchmark results are: {benchmark_line}"
        user_contents.append(user_content)

    _, benchmark_result, _, _ = previous_option_files[-1]
    benchmark_line = generate_benchmark_info(test_name, benchmark_result, average_cpu_used, average_mem_used)
    user_content = f"Part of the current option file is:\n```\n{chunk_string}\n```\nThe benchmark results are: {benchmark_line}"
    user_contents.append(user_content)
    user_contents.append("Based on these information generate a new file in same format as the options_file to improve my database performance. Enclose the new options file in ```.")
    return user_contents

def generate_benchmark_info(test_name, benchmark_result, average_cpu_used, average_mem_used):
    """
    Function to create a formatted string with benchmark information.

    Parameters:
    - test_name: Name of the test.
    - benchmark_result: Dictionary with benchmark results.
    - average_cpu_used: Average CPU usage.
    - average_mem_used: Average Memory usage.

    Returns:
    - A formatted string with all benchmark information.
    """
    benchmark_line = (f"The use case for the database is perfectly simulated by the {test_name} test. "
                      f"The db_bench benchmark results for {test_name} are: Write/Read speed: {benchmark_result['data_speed']} "
                      f"{benchmark_result['data_speed_unit']}, Operations per second: {benchmark_result['ops_per_sec']}.")
    
    if average_cpu_used != -1 and average_mem_used != -1:
        benchmark_line += f" CPU used: {average_cpu_used:.2f}%, Memory used: {average_mem_used:.2f}% during test."
    
    return benchmark_line

def midway_options_file_generation(options, avg_cpu_used, avg_mem_used, last_throughput, device_information, options_file):
    """
    Function to generate a prompt for the midway options file generation.
    
    Returns:
    - str: A prompt for the midway options file generation.
    """

    sys_content = (
        "You are a RocksDB Expert being consulted by a company to help improve their RocksDB performance "
        "by optimizing the options configured for a particular scenario they face."
        f"Only provide option files for rocksdb version {constants.VERSION}. Direct IO will always be used. "
        "Additionally, compression type is set to none always. "
        "Respond with the the reasoning first, then show the option file in original format."
        f"The Device information is: {device_information}"
    )

    user_content = []
    content = "Can you generate a new options file for RocksDB based on the following information?\n"
    content += "The previous options file is:\n"

    content += "```\n"
    content += options_file[-1][0]
    content += "```\n"

    content += (
        f"The throughput results for the above options file are: {options_file[-1][1]['ops_per_sec']}. "
    )

    user_content.append(content)
    content = ""

    content += "We then made the following changes to the options file:\n"

    pattern = re.compile(r'\s*([^=\s]+)\s*=\s*([^=\s]+)\s*')

    file1_lines = pattern.findall(options)
    file2_lines = pattern.findall(options_file[-1][0])

    file1_lines = ["{} = {}".format(k, v) for k, v in file1_lines]
    file2_lines = ["{} = {}".format(k, v) for k, v in file2_lines]
    differ = Differ()
    diff = list(differ.compare(file1_lines, file2_lines))
    lst= []
    for line in diff:
        if line.startswith('+'):
            lst.append(line)
    result = '\n'.join(line[2:] for line in lst)

    content += "```\n"
    content += result
    content += "```\n"

    content += f"\nThe updated file has a throughput of: {last_throughput}. \n\n"
    user_content.append(content)
    content = ""
    content += "Based on this information generate a new file. Enclose the new options in ```. Feel free to use upto 100% of the CPU and Memory."
    user_content.append(content)

    log_update("[OG] Generating options file with differences")
    log_update("[OG] Prompt for midway options file generation")
    log_update(content)

    matches = request_llm(sys_content, user_content, 0.4)

    if matches is not None:
        clean_options_file = cleanup_options_file(matches[1])
        reasoning = matches[0] + matches[2]
    else:
        raise ValueError("Failed to get a valid response from LLM for midway options generation.")

    return clean_options_file, reasoning

def generate_option_file_with_llm(previous_option_files, device_information, temperature=0.4, average_cpu_used=-1.0, average_mem_used=-1.0, test_name="fillrandom", version="8.8.1"):
    """
    Function that generates an options file for RocksDB based on specified parameters.
    
    Parameters:
    - previous_option_files (list): A list of tuples containing past options file configurations and other relevant data.
    - device_information (str): Information about the device/system on which RocksDB is running.
    - temperature (float, optional): Controls the randomness/creativity of the generated output. Default is 0.4.
    - average_cpu_used (float, optional): Average CPU usage, used for tuning the configuration. Default is -1.0, indicating not specified.
    - average_mem_used (float, optional): Average memory usage, used for tuning the configuration. Default is -1.0, indicating not specified.
    - test_name (str, optional): Identifier for the type of test or configuration scenario. Default is "fillrandom".
    - version (str, optional): The RocksDB version. Default is "8.8.1".

    Returns:
    - tuple: A tuple containing the generated options file, reasoning behind the options, and an empty string as a placeholder.
    """
    log_update("[OG] Generating options file with long option changes")
    print("[OG] Generating options file with long option changes")
    system_content = generate_system_content(device_information, version)
    previous_option_file, _, _, _ = previous_option_files[-1]
    user_contents = generate_default_user_content(previous_option_file, previous_option_files, average_cpu_used, average_mem_used, test_name)
    matches = request_llm(system_content, user_contents, temperature)
    
    clean_options_file = None
    reasoning = None
    # Process the Gemini-generated response 
    if matches is not None:
        clean_options_file = cleanup_options_file(matches[1])
        reasoning = matches[0] + matches[2]
    else:
        clean_options_file = None
        reasoning = None

    return clean_options_file, reasoning