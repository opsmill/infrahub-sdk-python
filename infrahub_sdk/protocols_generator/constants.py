TEMPLATE_FILE_NAME = "template.j2"

ATTRIBUTE_KIND_MAP = {
    "ID": "String",
    "Text": "String",
    "TextArea": "String",
    "DateTime": "DateTime",
    "Email": "String",
    "Password": "String",
    "HashedPassword": "HashedPassword",
    "URL": "URL",
    "File": "String",
    "MacAddress": "MacAddress",
    "Color": "String",
    "Dropdown": "Dropdown",
    "Number": "Integer",
    "Bandwidth": "Integer",
    "IPHost": "IPHost",
    "IPNetwork": "IPNetwork",
    "Boolean": "Boolean",
    "Checkbox": "Boolean",
    "List": "ListAttribute",
    "JSON": "JSONAttribute",
    "Any": "AnyAttribute",
}

# The order of the classes in the list determines the order of the classes in the generated code
CORE_BASE_CLASS_TO_SYNCIFY = ["CoreProfile", "CoreObjectTemplate", "CoreNode"]
