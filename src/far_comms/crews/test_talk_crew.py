from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

@CrewBase
class TestTalkCrew():
  """Test crew for generating social content using existing Coda Resources and Analysis"""
  agents_config = 'config/test_talk/agents.yaml'
  tasks_config = 'config/test_talk/tasks.yaml'
  
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
    
    # Claude 3.5 Haiku for simple/mechanical tasks (cost optimization)
    self.haiku_llm = LLM(
      model="anthropic/claude-3-5-haiku-20241022",
      max_retries=3
    )

  # COMMENTED OUT AGENTS - Using Coda data instead

  # @agent
  # def resource_researcher_agent(self) -> Agent:
  #   tools = []
  #   
  #   # Try Serper API first (Google search results)
  #   try:
  #       from crewai.tools import BaseTool
  #       import requests
  #       import json
  #       
  #       class SerperTool(BaseTool):
  #           name: str = "web_search"
  #           description: str = "Search the web using Serper API (Google results)"
  #           
  #           def _run(self, query: str) -> str:
  #               """Search using Serper API"""
  #               try:
  #                   api_key = os.getenv("SERPER_API_KEY")
  #                   if not api_key:
  #                       return "No search available - missing API key"
  #                   
  #                   url = "https://google.serper.dev/search"
  #                   payload = {"q": query, "num": 5}
  #                   headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
  #                   
  #                   response = requests.post(url, json=payload, headers=headers, timeout=10)
  #                   if response.status_code == 200:
  #                       data = response.json()
  #                       results = data.get("organic", [])[:3]
  #                       formatted = []
  #                       for r in results:
  #                           title = r.get("title", "No title")
  #                           link = r.get("link", "")
  #                           snippet = r.get("snippet", "")[:100]
  #                           formatted.append(f"{title} - {link}\\n{snippet}")
  #                       return "\\n\\n".join(formatted) if formatted else "No search results found."
  #                   else:
  #                       return f"Search failed: HTTP {response.status_code}"
  #               except Exception as e:
  #                   return f"Search error: {str(e)}"
  #       
  #       if os.getenv("SERPER_API_KEY"):
  #           search_tool = SerperTool()
  #           tools.append(search_tool)
  #           logger.info("Serper API search tool initialized successfully")
  #       else:
  #           logger.warning("No SERPER_API_KEY found")
  #           
  #   except Exception as e:
  #       logger.warning(f"Serper search tool failed: {e}")
  #   
  #   # Fallback to DuckDuckGo if Serper fails
  #   if not tools:
  #       try:
  #           from crewai.tools import BaseTool
  #           from duckduckgo_search import DDGS
  #           
  #           class DuckDuckGoTool(BaseTool):
  #               name: str = "web_search"
  #               description: str = "Search the web using DuckDuckGo"
  #               
  #               def _run(self, query: str) -> str:
  #                   """Search using DuckDuckGo"""
  #                   try:
  #                       with DDGS() as ddgs:
  #                           results = list(ddgs.text(query, max_results=3))
  #                           if not results:
  #                               return "No search results found."
  #                           
  #                           formatted = []
  #                           for r in results:
  #                               title = r.get('title', 'No title')
  #                               link = r.get('href', '')
  #                               body = r.get('body', '')[:100]
  #                               formatted.append(f"{title} - {link}\\n{body}")
  #                           return "\\n\\n".join(formatted)
  #                   except Exception as e:
  #                       return f"Search failed: {str(e)}"
  #           
  #           search_tool = DuckDuckGoTool()
  #           tools.append(search_tool)
  #           logger.info("DuckDuckGo search tool initialized as fallback")
  #       except ImportError as e:
  #           logger.warning(f"DuckDuckGo search not available: {e}")
  #   
  #   if not tools:
  #       logger.warning("No web search tools available - agent will work with slides only")
  #   
  #   return Agent(
  #       config=self.agents_config['resource_researcher_agent'],
  #       llm=self.sonnet_llm,  # Complex validation needed - Sonnet
  #       verbose=True,
  #       allow_delegation=False,
  #       tools=tools
  #   )

  # @agent
  # def transcript_analyzer_agent(self) -> Agent:
  #   return Agent(
  #       config=self.agents_config['transcript_analyzer_agent'],
  #       llm=self.opus_llm,  # Upgraded to Opus for combined analysis + creative hook generation
  #       verbose=True,
  #       allow_delegation=False
  #   )

  @agent  
  def summarizer_agent(self) -> Agent:
    return Agent(
        config=self.agents_config['summarizer_agent'],
        llm=self.sonnet_llm,  # Style compliance crucial - Sonnet
        verbose=True,
        allow_delegation=False
    )


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
    from far_comms.tools import CharacterCounterTool
    
    return Agent(
      config=self.agents_config['x_content_writer_agent'],
      llm=self.opus_llm,  # Content creation - Opus
      verbose=True,
      allow_delegation=False,
      tools=[CharacterCounterTool()]
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

  # Phase 4: Final QA

  @agent
  def final_qa_agent(self) -> Agent:
    from far_comms.tools import CharacterCounterTool
    
    # Final QA assembles content from context and makes final decisions
    return Agent(
      config=self.agents_config['final_qa_agent'],
      llm=self.opus_llm,  # Complex final decisions - Opus
      verbose=True,
      allow_delegation=True,  # Allow targeted quality questions only
      tools=[CharacterCounterTool()]
    )

  # Tasks - Modified Sequential Workflow
  
  # COMMENTED OUT TASKS - Using Coda data instead
  # @task
  # def research_resources_task(self) -> Task:
  #     return Task(
  #         config=self.tasks_config['research_resources_task'],
  #         agent=self.resource_researcher_agent()
  #     )

  # @task
  # def analyze_transcript_task(self) -> Task:
  #     return Task(
  #         config=self.tasks_config['analyze_transcript_task'],
  #         agent=self.transcript_analyzer_agent()
  #     )

  @task
  def generate_summaries_task(self) -> Task:
    return Task(
        config=self.tasks_config['generate_summaries_task'],
        agent=self.summarizer_agent()
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
  def brand_voice_check_task(self) -> Task:
    return Task(
      config=self.tasks_config['brand_voice_check_task'],
      agent=self.voice_checker_agent()
    )




  @task
  def final_qa_task(self) -> Task:
    return Task(
      config=self.tasks_config['final_qa_task'],
      agent=self.final_qa_agent()
    )

  @crew
  def crew(self) -> Crew:
    """Creates the TestTalk crew with modified workflow using existing Coda data"""

    return Crew(
      agents=[
        # COMMENTED OUT - Using Coda data instead
        # self.resource_researcher_agent(),
        # self.transcript_analyzer_agent(),
        self.summarizer_agent(),
        self.li_content_writer_agent(),
        self.x_content_writer_agent(),
        self.fact_checker_agent(),
        self.voice_checker_agent(),
        self.final_qa_agent()
      ],
      tasks=[
        # Modified workflow - starts from summarizer using Coda Resources and Analysis
        # COMMENTED OUT - Using Coda data instead
        # self.research_resources_task(),
        # self.analyze_transcript_task(),
        self.generate_summaries_task(),
        self.create_li_content_task(),
        self.create_x_content_task(),
        # Evaluation pipeline
        self.fact_check_content_task(),
        self.brand_voice_check_task(),
        # Final QA and assembly
        self.final_qa_task()
      ],
      process=Process.sequential,
      verbose=True
    )