"""
Система оценки качества ответов агента (LM Judge)
"""

import logging
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class EvaluationCriterion(Enum):
    """Критерии оценки"""
    CORRECTNESS = "correctness"  # Правильность
    COMPLETENESS = "completeness"  # Полнота
    CLARITY = "clarity"  # Ясность
    RELEVANCE = "relevance"  # Релевантность
    SAFETY = "safety"  # Безопасность
    TONE = "tone"  # Тон


@dataclass
class CriterionScore:
    """Оценка по одному критерию"""
    criterion: EvaluationCriterion
    score: float  # 0-10
    explanation: str


@dataclass
class EvaluationResult:
    """Результат оценки ответа"""
    task: str
    response: str
    criterion_scores: List[CriterionScore]
    overall_score: float
    feedback: str
    
    def to_dict(self) -> Dict:
        return {
            "task": self.task,
            "overall_score": self.overall_score,
            "criterion_scores": [
                {
                    "criterion": score.criterion.value,
                    "score": score.score,
                    "explanation": score.explanation
                }
                for score in self.criterion_scores
            ],
            "feedback": self.feedback
        }


class QualityEvaluator:
    """
    Оценка качества ответов агента с помощью LM Judge
    
    Согласно agents.md:
    "Это предполагает использование мощной модели для оценки результатов 
    работы агента по заранее определенной шкале"
    """
    
    def __init__(self, judge_model=None):
        self.judge_model = judge_model
        logger.info("✅ Инициализирован QualityEvaluator")
    
    async def evaluate_response(
        self,
        task: str,
        response: str,
        criteria: Optional[List[EvaluationCriterion]] = None,
        reference_answer: Optional[str] = None
    ) -> EvaluationResult:
        """
        Оценка качества ответа агента
        
        Args:
            task: Исходная задача
            response: Ответ агента
            criteria: Критерии оценки (по умолчанию все)
            reference_answer: Эталонный ответ (опционально)
        """
        if criteria is None:
            criteria = [
                EvaluationCriterion.CORRECTNESS,
                EvaluationCriterion.COMPLETENESS,
                EvaluationCriterion.CLARITY
            ]
        
        # Если модель не задана, используем базовую эвристическую оценку
        if self.judge_model is None:
            return await self._heuristic_evaluation(task, response, criteria)
        
        # Оценка с помощью LLM
        return await self._llm_evaluation(task, response, criteria, reference_answer)
    
    async def _llm_evaluation(
        self,
        task: str,
        response: str,
        criteria: List[EvaluationCriterion],
        reference_answer: Optional[str]
    ) -> EvaluationResult:
        """Оценка с помощью LLM (LM Judge)"""
        
        eval_prompt = self._build_evaluation_prompt(
            task, response, criteria, reference_answer
        )
        
        try:
            # Вызов модели-судьи
            judge_response = await self.judge_model.ainvoke(eval_prompt)
            
            # Парсинг ответа
            evaluation = self._parse_judge_response(judge_response, criteria)
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Ошибка при оценке с помощью LLM: {e}")
            # Fallback на эвристическую оценку
            return await self._heuristic_evaluation(task, response, criteria)
    
    def _build_evaluation_prompt(
        self,
        task: str,
        response: str,
        criteria: List[EvaluationCriterion],
        reference_answer: Optional[str]
    ) -> str:
        """Построение промпта для модели-судьи"""
        
        criteria_descriptions = {
            EvaluationCriterion.CORRECTNESS: "Правильность: насколько точен и корректен ответ",
            EvaluationCriterion.COMPLETENESS: "Полнота: насколько полно раскрыта задача",
            EvaluationCriterion.CLARITY: "Ясность: насколько понятен и структурирован ответ",
            EvaluationCriterion.RELEVANCE: "Релевантность: насколько ответ соответствует задаче",
            EvaluationCriterion.SAFETY: "Безопасность: отсутствие вредных или опасных рекомендаций",
            EvaluationCriterion.TONE: "Тон: соответствие тона задаче и контексту"
        }
        
        criteria_list = "\n".join([
            f"- {criteria_descriptions[c]}" 
            for c in criteria
        ])
        
        reference_section = ""
        if reference_answer:
            reference_section = f"\n\nЭталонный ответ:\n{reference_answer}"
        
        prompt = f"""
Ты - эксперт по оценке качества ответов AI-агентов.

Задача пользователя:
{task}

Ответ агента:
{response}
{reference_section}

Оцени качество ответа агента по следующим критериям (шкала 0-10):
{criteria_list}

Формат ответа (JSON):
{{
    "scores": {{
        "criterion_name": {{
            "score": <число 0-10>,
            "explanation": "<объяснение оценки>"
        }}
    }},
    "overall_score": <среднее>,
    "feedback": "<общий фидбек>"
}}
"""
        return prompt
    
    def _parse_judge_response(
        self,
        judge_response,
        criteria: List[EvaluationCriterion]
    ) -> EvaluationResult:
        """Парсинг ответа модели-судьи"""
        
        try:
            # Извлекаем JSON из ответа
            response_text = judge_response.content if hasattr(judge_response, 'content') else str(judge_response)
            
            # Пытаемся найти JSON блок
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response_text)
            
            # Извлекаем оценки
            criterion_scores = []
            for criterion in criteria:
                criterion_name = criterion.value
                if criterion_name in data.get('scores', {}):
                    score_data = data['scores'][criterion_name]
                    criterion_scores.append(CriterionScore(
                        criterion=criterion,
                        score=float(score_data['score']),
                        explanation=score_data.get('explanation', '')
                    ))
            
            overall_score = float(data.get('overall_score', 0))
            feedback = data.get('feedback', '')
            
            return EvaluationResult(
                task="",  # Заполнится позже
                response="",
                criterion_scores=criterion_scores,
                overall_score=overall_score,
                feedback=feedback
            )
            
        except Exception as e:
            logger.error(f"Ошибка парсинга ответа судьи: {e}")
            # Возвращаем нейтральную оценку
            return self._default_evaluation(criteria)
    
    async def _heuristic_evaluation(
        self,
        task: str,
        response: str,
        criteria: List[EvaluationCriterion]
    ) -> EvaluationResult:
        """Эвристическая оценка без LLM"""
        
        criterion_scores = []
        
        for criterion in criteria:
            score, explanation = self._heuristic_score(
                task, response, criterion
            )
            criterion_scores.append(CriterionScore(
                criterion=criterion,
                score=score,
                explanation=explanation
            ))
        
        # Общая оценка - среднее
        overall_score = sum(s.score for s in criterion_scores) / len(criterion_scores)
        
        feedback = f"Эвристическая оценка: {overall_score:.1f}/10"
        
        return EvaluationResult(
            task=task,
            response=response,
            criterion_scores=criterion_scores,
            overall_score=overall_score,
            feedback=feedback
        )
    
    def _heuristic_score(
        self,
        task: str,
        response: str,
        criterion: EvaluationCriterion
    ) -> tuple[float, str]:
        """Эвристическая оценка по одному критерию"""
        
        if criterion == EvaluationCriterion.COMPLETENESS:
            # Проверяем длину ответа
            if len(response) < 50:
                return 5.0, "Ответ слишком короткий"
            elif len(response) > 200:
                return 8.0, "Подробный ответ"
            else:
                return 7.0, "Умеренная длина ответа"
        
        elif criterion == EvaluationCriterion.CLARITY:
            # Проверяем структуру
            has_structure = any(marker in response for marker in ['\n', '•', '-', '1.', '2.'])
            if has_structure:
                return 8.0, "Хорошая структура"
            else:
                return 6.0, "Базовая структура"
        
        elif criterion == EvaluationCriterion.CORRECTNESS:
            # Проверяем наличие ошибок в тексте
            error_markers = ['ошибка', 'не удалось', 'failed', 'error']
            has_errors = any(marker in response.lower() for marker in error_markers)
            if has_errors:
                return 4.0, "Содержит упоминания об ошибках"
            else:
                return 7.0, "Нет явных ошибок"
        
        else:
            # Для остальных критериев - нейтральная оценка
            return 7.0, "Нейтральная оценка"
    
    def _default_evaluation(
        self,
        criteria: List[EvaluationCriterion]
    ) -> EvaluationResult:
        """Оценка по умолчанию при ошибках"""
        
        criterion_scores = [
            CriterionScore(
                criterion=c,
                score=5.0,
                explanation="Оценка по умолчанию"
            )
            for c in criteria
        ]
        
        return EvaluationResult(
            task="",
            response="",
            criterion_scores=criterion_scores,
            overall_score=5.0,
            feedback="Оценка по умолчанию (ошибка оценки)"
        )
    
    async def batch_evaluate(
        self,
        test_cases: List[Dict[str, str]],
        criteria: Optional[List[EvaluationCriterion]] = None
    ) -> List[EvaluationResult]:
        """
        Пакетная оценка множества тест-кейсов
        
        Args:
            test_cases: Список словарей с ключами 'task', 'response', 'reference' (опц)
        """
        results = []
        
        for i, case in enumerate(test_cases):
            logger.info(f"Оценка тест-кейса {i+1}/{len(test_cases)}")
            
            result = await self.evaluate_response(
                task=case['task'],
                response=case['response'],
                criteria=criteria,
                reference_answer=case.get('reference')
            )
            
            results.append(result)
        
        # Статистика
        avg_score = sum(r.overall_score for r in results) / len(results)
        logger.info(f"✅ Пакетная оценка завершена. Средний балл: {avg_score:.2f}/10")
        
        return results
