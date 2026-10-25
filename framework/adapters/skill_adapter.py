from __future__ import annotations
from typing import Any, Dict
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from skill_contracts.skill_spec import SkillSpec


class SkillAdapter:
    @staticmethod
    def skill_to_task_contract(skill: SkillSpec) -> Dict[str, Any]:
        return {
            'agent': skill.name.split('.')[-2] if '.' in skill.name else 'implementer',
            'objective': skill.persona[:200],
            'expected_artifact': f'Output matching skill contract for {skill.name}',
            'context': {'skill_spec': {'name': skill.name, 'model': skill.model, 'reasoning': skill.reasoning, 'tools': [t.name for t in skill.tools], 'risk': skill.risk, 'max_iterations': skill.max_iterations}},
            'completion_criteria': [{'type': 'skill_validation', 'skill_name': skill.name}],
        }
    
    @staticmethod
    def validate_skill_for_enforcement(skill: SkillSpec) -> list:
        problems = skill.validate()
        if skill.risk == 'high' and skill.fallback != 'escalate':
            problems.append('high risk skills must fallback to escalate for human review')
        if not skill.eval_set:
            problems.append('skills must have eval_set for production use')
        return problems

