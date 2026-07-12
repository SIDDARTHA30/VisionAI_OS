from pydantic import BaseModel, Field


class BrowserAction(BaseModel):
    action: str = Field(..., description="Action to perform: navigate, click, type, scrape, screenshot")
    url: str = Field(None, description="Target URL")
    selector: str = Field(None, description="CSS selector for target element")
    value: str = Field(None, description="Input string value to type")
