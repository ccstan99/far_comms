from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class PromoteTalkCrew():
  """Crew to generate summary + social content for FAR.AI event talks"""
  agents_config = 'config/promote_talk/agents.yaml'
  tasks_config = 'config/promote_talk/tasks.yaml'
  
  def __init__(self):
    # High-quality Claude 4.1 Opus for content creation and final review
    self.opus_llm = LLM(
      model="anthropic/claude-opus-4-1-20250805",
      max_retries=3
    )
    
    # Claude 4 Sonnet for analytical/systematic tasks
    self.sonnet_llm = LLM(
      model="anthropic/claude-sonnet-4-20250514",
      max_retries=3
    )

  # Multi-Agent Architecture - Phase 1: Content Creation (Analysis now comes from prepare-talk)

  # Removed hook_specialist_agent - LI and X writers now generate their own hooks for better alignment

  # Phase 2: Content Creation
  @agent
  def li_content_writer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['li_content_writer_agent'],
      llm=self.opus_llm,  # Content creation - Opus
      verbose=True,
      allow_delegation=False
    )

  @agent
  def x_content_writer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['x_content_writer_agent'],
      llm=self.opus_llm,  # Content creation - Opus
      verbose=True,
      allow_delegation=False
    )

  # Phase 3: Quality Control
  @agent
  def fact_checker_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['fact_checker_agent'],
      llm=self.sonnet_llm,  # Systematic checking - Sonnet
      verbose=True,
      allow_delegation=False
    )

  @agent
  def voice_checker_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['voice_checker_agent'],
      llm=self.sonnet_llm,  # Rule-based checking - Sonnet
      verbose=True,
      allow_delegation=False
    )

  # Phase 4: Final Review

  @agent
  def final_reviewer_agent(self) -> Agent:
    # Final reviewer should not delegate - it's the final stage that iterates on itself
    return Agent(
      config=self.agents_config['final_reviewer_agent'],
      llm=self.opus_llm,  # Final quality control - Opus
      verbose=True,
      allow_delegation=False
    )

  # Tasks - Sequential Multi-Agent Workflow (Analysis now comes from prepare-talk)

  # Removed generate_hooks_task - hooks now generated inline by content writers

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
        self.li_content_writer_agent(),
        self.x_content_writer_agent(),
        self.fact_checker_agent(),
        self.voice_checker_agent(),
        self.final_reviewer_agent()
      ],
      tasks=[
        self.create_li_content_task(),
        self.create_x_content_task(),
        self.fact_check_content_task(),
        self.voice_authenticity_check_task(),
        self.final_review_task()
      ],
      process=Process.sequential,
      verbose=True
    )