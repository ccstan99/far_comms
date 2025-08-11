import logging
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

logger = logging.getLogger(__name__)

@CrewBase
class PrepareTalkCrew():
    """Crew to prepare talk content by processing slides and transcripts"""
    agents_config = 'config/prepare_talk/agents.yaml'
    tasks_config = 'config/prepare_talk/tasks.yaml'
    
    def __init__(self):
        # Use Claude 4 Sonnet for systematic processing tasks
        self.sonnet_llm = LLM(
            model="anthropic/claude-sonnet-4-20250514",
            max_retries=3
        )
        
        # Preprocessing is done in the handler, agents work with clean data

    # Processing Agents
    @agent
    def slide_processor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['slide_processor_agent'],
            llm=self.sonnet_llm,
            verbose=True,
            allow_delegation=False
        )

    @agent
    def transcript_processor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['transcript_processor_agent'],
            llm=self.sonnet_llm,
            verbose=True,
            allow_delegation=False
        )


    # Sequential Processing Tasks
    @task
    def process_slides_task(self) -> Task:
        return Task(
            config=self.tasks_config['process_slides_task'],
            agent=self.slide_processor_agent()
        )

    @task
    def process_transcript_task(self) -> Task:
        return Task(
            config=self.tasks_config['process_transcript_task'],
            agent=self.transcript_processor_agent()
        )


    @task
    def final_assembly_task(self) -> Task:
        return Task(
            config=self.tasks_config['final_assembly_task'],
            agent=self.slide_processor_agent()  # Use slide processor for final assembly
        )

    @crew
    def crew(self) -> Crew:
        """Creates the PrepareTalk processing crew"""
        return Crew(
            agents=[
                self.slide_processor_agent(),
                self.transcript_processor_agent()
            ],
            tasks=[
                self.process_slides_task(),
                self.process_transcript_task(),
                self.final_assembly_task()
            ],
            process=Process.sequential,
            verbose=True
        )