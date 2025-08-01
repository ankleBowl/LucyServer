class Message:
    def __init__(self, type_, content):
        self.type_ = type_
        self.content = content

    def to_openai(self):
        if self.type_ == "system":
            return {
                "role": "system",
                "content": self.content
            }
        
        role = "assistant"
        content = f"<{self.type_}>{self.content}</{self.type_}>"
        if self.type_ == "user" or self.type_ == "tool_response" or self.type_ == "error":
            role = "user"

        return {
            "role": role,
            "content": content
        }
    
    def __str__(self):
        return f"{self.type_}: {self.content}"
    
    def to_json(self):
        return {
            "type": self.type_,
            "content": self.content
        }