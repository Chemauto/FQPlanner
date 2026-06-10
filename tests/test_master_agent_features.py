import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MASTER_DIR = PROJECT_ROOT / "master"
if str(MASTER_DIR) not in sys.path:
    sys.path.insert(0, str(MASTER_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.agent import GlobalAgent, TaskQueue


class MasterAgentFeatureTests(unittest.TestCase):
    def test_task_queue_records_status(self):
        q = TaskQueue([
            {"robot_name": "FQrobot", "subtask": "抓取 apple", "subtask_order": 1},
            {"robot_name": "FQrobot", "subtask": "放到 counter", "subtask_order": 2},
        ])

        first = q.get_next_undone()
        q.mark_done(first, status="failure")

        completed = q.get_completed()
        self.assertIs(completed[0]["done"], True)
        self.assertEqual(completed[0]["status"], "failure")
        self.assertEqual(q.get_remaining()[0]["subtask"], "放到 counter")

    def test_skill_name_classification_without_constructor(self):
        get_skill = GlobalAgent._get_skill_name

        self.assertEqual(get_skill(None, "抓取 mug"), "grasp")
        self.assertEqual(get_skill(None, "place the mug on counter"), "place")
        self.assertEqual(get_skill(None, "导航到 apple"), "navigate")
        self.assertEqual(get_skill(None, "整理桌面然后检查"), "multi_step")

    def test_load_experiences_reads_skill_and_multi_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            agent = object.__new__(GlobalAgent)
            agent.current_task_desc = "抓取 mug"
            agent._skills_dir = str(tmp_path / "skills")
            agent._experience_file = str(tmp_path / "experiences.md")
            agent._exploration_rate = 0.5
            os.makedirs(agent._skills_dir)
            Path(agent._skills_dir, "grasp.md").write_text(
                "# grasp\n\n## 避免规则\n- 规则：抓取前先靠近\n",
                encoding="utf-8",
            )
            Path(agent._skills_dir, "multi_step.md").write_text(
                "# multi\n\n## 正向经验\n- 策略：先导航再操作\n",
                encoding="utf-8",
            )

            text = agent._load_experiences("抓取 mug")

            self.assertIn("grasp 专项经验", text)
            self.assertIn("复合任务经验", text)
            self.assertIn("抓取前先靠近", text)
            self.assertIn("先导航再操作", text)


if __name__ == "__main__":
    unittest.main()
