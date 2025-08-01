from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class FarCommsCrew():
  """Crew to generate summary + social content for FAR.AI event talks"""
  agents_config = 'config/promote_talk/agents.yaml'
  tasks_config = 'config/promote_talk/tasks.yaml'

  # Agents
  @agent
  def summarizer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['summarizer_agent'],
      verbose=True,
      allow_delegation=False
    )

  @agent
  def li_writer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['li_writer_agent'],
      verbose=True,
      allow_delegation=False
    )

  @agent
  def twitter_writer_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['twitter_writer_agent'],
      verbose=True,
      allow_delegation=False
    )

  @agent
  def fact_checker_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['fact_checker_agent'],
      verbose=True,
      allow_delegation=False
    )
  
  @agent
  def editor_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['editor_agent'],
      verbose=True,
      allow_delegation=False
    )

  @agent
  def qa_agent(self) -> Agent:
    return Agent(
      config=self.agents_config['qa_agent'],
      verbose=True,
      allow_delegation=True
    )

  # Tasks
  @task
  def generate_summary_task(self) -> Task:
    return Task(
      config=self.tasks_config['generate_summary_task'],
      agent=self.summarizer_agent()
    )

  @task
  def generate_linkedin_post_task(self) -> Task:
    return Task(
      config=self.tasks_config['generate_linkedin_post_task'],
      agent=self.li_writer_agent()
    )

  @task
  def generate_twitter_thread_task(self) -> Task:
    return Task(
      config=self.tasks_config['generate_twitter_thread_task'],
      agent=self.twitter_writer_agent()
    )

  @task
  def fact_check_comms_task(self) -> Task:
    return Task(
      config=self.tasks_config['fact_check_comms_task'],
      agent=self.fact_checker_agent()
    )
  
  @task
  def tighten_linkedin_post_task(self) -> Task:
    return Task(
      config=self.tasks_config['tighten_linkedin_post_task'],
      agent=self.editor_agent()
    )

  @task
  def tighten_twitter_thread_task(self) -> Task:
    return Task(
      config=self.tasks_config['tighten_twitter_thread_task'],
      agent=self.editor_agent()
    )
  
  @task
  def qa_review_task(self) -> Task:
    return Task(
      config=self.tasks_config['qa_review_task'],
      agent=self.qa_agent()
    )

  @crew
  def crew(self) -> Crew:
    """Creates the FarComms crew"""

    return Crew(
      agents=[
        self.summarizer_agent(),
        self.li_writer_agent(),
        self.twitter_writer_agent(),
        self.fact_checker_agent(),
        self.editor_agent(),
        self.qa_agent()
      ],
      tasks=[
        self.generate_summary_task(),
        self.generate_linkedin_post_task(),
        self.tighten_linkedin_post_task(),
        self.generate_twitter_thread_task(),
        self.tighten_twitter_thread_task(),
        self.fact_check_comms_task(),
        self.qa_review_task()
      ],
      process=Process.sequential,
      verbose=True
    )