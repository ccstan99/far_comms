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
        tools = []
        
        # Try Serper API first (Google search results)
        try:
            from crewai.tools import BaseTool
            import requests
            import json
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            class SerperTool(BaseTool):
                name: str = "web_search"
                description: str = "Search the web using Serper API (Google results)"
                
                def _run(self, query: str) -> str:
                    """Search using Serper API"""
                    try:
                        api_key = os.getenv("SERPER_API_KEY")
                        if not api_key:
                            return "No search available - missing API key"
                        
                        url = "https://google.serper.dev/search"
                        payload = {"q": query, "num": 5}
                        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
                        
                        response = requests.post(url, json=payload, headers=headers, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            results = data.get("organic", [])[:3]
                            formatted = []
                            for r in results:
                                title = r.get("title", "No title")
                                link = r.get("link", "")
                                snippet = r.get("snippet", "")[:100]
                                formatted.append(f"{title} - {link}\n{snippet}")
                            return "\n\n".join(formatted) if formatted else "No search results found."
                        else:
                            return f"Search failed: HTTP {response.status_code}"
                    except Exception as e:
                        return f"Search error: {str(e)}"
            
            if os.getenv("SERPER_API_KEY"):
                search_tool = SerperTool()
                tools.append(search_tool)
                logger.info("Serper API search tool initialized successfully")
            else:
                logger.warning("No SERPER_API_KEY found")
                
        except Exception as e:
            logger.warning(f"Serper search tool failed: {e}")
        
        # Fallback to DuckDuckGo if Serper fails
        if not tools:
            try:
                from crewai.tools import BaseTool
                from duckduckgo_search import DDGS
                
                class DuckDuckGoTool(BaseTool):
                    name: str = "web_search"
                    description: str = "Search the web using DuckDuckGo"
                    
                    def _run(self, query: str) -> str:
                        """Search using DuckDuckGo"""
                        try:
                            with DDGS() as ddgs:
                                results = list(ddgs.text(query, max_results=3))
                                if not results:
                                    return "No search results found."
                                
                                formatted = []
                                for r in results:
                                    title = r.get('title', 'No title')
                                    link = r.get('href', '')
                                    body = r.get('body', '')[:100]
                                    formatted.append(f"{title} - {link}\n{body}")
                                return "\n\n".join(formatted)
                        except Exception as e:
                            return f"Search failed: {str(e)}"
                
                search_tool = DuckDuckGoTool()
                tools.append(search_tool)
                logger.info("DuckDuckGo search tool initialized as fallback")
            except ImportError as e:
                logger.warning(f"DuckDuckGo search not available: {e}")
        
        if not tools:
            logger.warning("No web search tools available - agent will work with slides only")
        
        
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
            ],
            tasks=[
                self.research_resources_task(),
            ],
            process=Process.sequential,
            verbose=True
        )