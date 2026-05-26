import enum 

class UserTypeEnum(str , enum.Enum):
    ADMIN = "ADMIN"
    NORMAL_USER = "NORMAL_USER"
    
    
class FileTypeEnum(str , enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"