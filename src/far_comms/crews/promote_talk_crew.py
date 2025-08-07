from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class PromoteTalkCrew():
  """Crew to generate summary + social content for FAR.AI event talks"""
  agents_config = 'config/promote_talk/agents.yaml'
  tasks_config = 'config/promote_talk/tasks.yaml'
  
  def __init__(self):
    self.llm = LLM(
      model="anthropic/claude-opus-4-20250514",
      max_retries=3
    )

  # Multi-Agent Architecture - Phase 1: Foundation
  @agent
  def transcript_analyzer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['transcript_analyzer_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  @agent
  def hook_specialist_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['hook_specialist_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  # Phase 2: Content Creation
  @agent
  def li_content_writer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['li_content_writer_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  @agent
  def x_content_writer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['x_content_writer_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  # Phase 3: Quality Control
  @agent
  def fact_checker_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['fact_checker_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  @agent
  def voice_checker_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['voice_checker_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  @agent
  def compliance_auditor_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['compliance_auditor_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=False
    )

  # Phase 4: Final Review

  @agent
  def final_reviewer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['final_reviewer_agent'],
      llm=self.llm,
      verbose=True,
      allow_delegation=True
    )

  # Tasks - Sequential Multi-Agent Workflow
  @task
  def analyze_transcript_task(self) -> Task:
    return Task(
      config=self.tasks_config['analyze_transcript_task'],
      agent=self.transcript_analyzer_agent()
    )

  @task
  def generate_hooks_task(self) -> Task:
    return Task(
      config=self.tasks_config['generate_hooks_task'],
      agent=self.hook_specialist_agent()
    )

  @task
  def create_li_content_task(self) -> Task:
    return Task(
      config=self.tasks_config['create_li_content_task'],
      agent=self.li_content_writer_agent()
    )

  @task
  def create_x_content_task(self) -> Task:
    return Task(
      config=self.tasks_config['create_x_content_task'],
      agent=self.x_content_writer_agent()
    )

  @task
  def fact_check_content_task(self) -> Task:
    return Task(
      config=self.tasks_config['fact_check_content_task'],
      agent=self.fact_checker_agent()
    )

  @task
  def voice_authenticity_check_task(self) -> Task:
    return Task(
      config=self.tasks_config['voice_authenticity_check_task'],
      agent=self.voice_checker_agent()
    )

  @task
  def compliance_audit_task(self) -> Task:
    return Task(
      config=self.tasks_config['compliance_audit_task'],
      agent=self.compliance_auditor_agent()
    )


  @task
  def final_review_task(self) -> Task:
    return Task(
      config=self.tasks_config['final_review_task'],
      agent=self.final_reviewer_agent()
    )

  @crew
  def crew(self) -> Crew:
    """Creates the Multi-Agent PromoteTalk crew"""

    return Crew(
      agents=[
        self.transcript_analyzer_agent(),
        self.hook_specialist_agent(),
        self.li_content_writer_agent(),
        self.x_content_writer_agent(),
        self.fact_checker_agent(),
        self.voice_checker_agent(),
        self.compliance_auditor_agent(),
        self.final_reviewer_agent()
      ],
      tasks=[
        self.analyze_transcript_task(),
        self.generate_hooks_task(),
        self.create_li_content_task(),
        self.create_x_content_task(),
        self.fact_check_content_task(),
        self.voice_authenticity_check_task(),
        self.compliance_audit_task(),
        self.final_review_task()
      ],
      process=Process.sequential,
      verbose=True
    )