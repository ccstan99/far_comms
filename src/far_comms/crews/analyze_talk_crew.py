import logging
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task

logger = logging.getLogger(__name__)

@CrewBase
class AnalyzeTalkCrew():
    """Crew to analyze existing slides/transcript content for resources and insights"""
    agents_config = 'config/analyze_talk/agents.yaml'
    tasks_config = 'config/analyze_talk/tasks.yaml'
    
    def __init__(self):
        # Use Claude 4 Sonnet for analytical tasks
        self.sonnet_llm = LLM(
            model="anthropic/claude-sonnet-4-20250514",
            max_retries=3
        )

    # Analysis Agents
    @agent
    def resource_researcher_agent(self) -> Agent:
        try:
            from langchain_community.tools import SerperSearchResults
            search_tool = SerperSearchResults()
            tools = [search_tool]
        except ImportError:
            # Fallback to no tools if SerperSearchResults not available
            tools = []
        
        return Agent(
            config=self.agents_config['resource_researcher_agent'],
            llm=self.sonnet_llm,
            verbose=True,
            allow_delegation=False,
            tools=tools
        )

    @agent
    def transcript_analyzer_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['transcript_analyzer_agent'],
            llm=self.sonnet_llm,
            verbose=True,
            allow_delegation=False
        )

    # Analysis Tasks
    @task
    def research_resources_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_resources_task'],
            agent=self.resource_researcher_agent()
        )

    @task
    def analyze_transcript_task(self) -> Task:
        return Task(
            config=self.tasks_config['analyze_transcript_task'],
            agent=self.transcript_analyzer_agent()
        )

    @task
    def final_assembly_task(self) -> Task:
        return Task(
            config=self.tasks_config['final_assembly_task'],
            agent=self.resource_researcher_agent()  # Use resource researcher for final assembly
        )

    @crew
    def crew(self) -> Crew:
        """Creates the AnalyzeTalk crew"""
        return Crew(
            agents=[
                self.resource_researcher_agent(),
                self.transcript_analyzer_agent()
            ],
            tasks=[
                self.research_resources_task(),
                self.analyze_transcript_task(),
                self.final_assembly_task()
            ],
            process=Process.sequential,
            verbose=True
        )