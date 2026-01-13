MASTER_PLANNING_PLANNING = """

Please only use {robot_name_list} with skills {robot_tools_info}.
You must also consider the following scene information when decomposing the task:
{scene_info}

Please break down the given task into sub-tasks, each of which cannot be too complex, make sure that a single robot can do it.

## CRITICAL RULES - DO NOT DECOMPOSE THESE TASKS:

The following task types MUST be passed directly to the robot WITHOUT any decomposition:
1. **Grasp-related tasks**: Any task containing "抓取" (grasp), "抓" (catch), "grasp", "pick up", etc.
   - These map directly to the `grasp_object` tool
   - Examples: "抓取", "抓取方块", "执行抓取", "grasp object", "抓取物体"
   - DO NOT add navigation, DO NOT add gripper control, DO NOT break into steps

2. **Status check tasks**: Any task asking to check/verify status
   - Examples: "检查抓取状态", "check status"

3. **Any task that can be completed by a single direct tool call**

For these direct-call tasks, simply set the "subtask" field to the original task text. Do not add any navigation, preparation, or intermediate steps.

Each sub-task in the output needs a concise name of the sub-task, which includes the robots that need to complete the sub-task.
Additionally you need to give a reasoning explanation on subtask decomposition and analyze if each step can be done by a single robot based on each robot's tools!

## The output format is as follows, in the form of a JSON structure:
{{
    "reasoning_explanation": xxx,
    "subtask_list": [
        {{"robot_name": xxx, "subtask": xxx, "subtask_order": xxx}},
        {{"robot_name": xxx, "subtask": xxx, "subtask_order": xxx}},
        {{"robot_name": xxx, "subtask": xxx, "subtask_order": xxx}},
    ]
}}

## Note: 'subtask_order' means the order of the sub-task. 
If the tasks are not sequential, please set the same 'task_order' for the same task. For example, if two robots are assigned to the two tasks, both of which are independance, they should share the same 'task_order'.
If the tasks are sequential, the 'task_order' should be set in the order of execution. For example, if the task_2 should be started after task_1, they should have different 'task_order'.

# The task to be completed is: {task}. Your output answer:
"""
