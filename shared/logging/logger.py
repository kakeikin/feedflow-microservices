# Reference: structured JSON logging pattern for future use
#
# import logging, json
#
# class JSONFormatter(logging.Formatter):
#     def format(self, record):
#         return json.dumps({
#             "level": record.levelname,
#             "message": record.getMessage(),
#             "service": record.__dict__.get("service", "unknown"),
#         })
