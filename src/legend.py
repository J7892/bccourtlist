"""
Legend reference and code decoders for BC Criminal Court Lists.
Reference: https://www2.gov.bc.ca/gov/content/justice/courthouse-services/daily-court-lists/criminal-court-lists
"""

COLUMN_EXPLANATIONS = {
    "Age": "Age of file (days or months)",
    "Agency File": "Code of agency and their file number",
    "Bail Proc": "Bail status or process (e.g. WAR = Warrant, UTP = Undertaking to Appear)",
    "By V/C": "By videoconference",
    "Case/File Number": "Court file number",
    "Cnt": "Count number",
    "Comments": "Comments on file",
    "Counsel": "Defense lawyer's name",
    "Court Clerk/Reporter": "Name of attending court clerk/reporter",
    "Description": "Legislation name and section number of alleged offence",
    "Disposition": "Results/Sentence of court (e.g., SOP, PNI, APG)",
    "I/C": "Custody status (Y = In Custody, N = Not in Custody)",
    "Justice": "Name of judge",
    "Lesser included": "Legislation name and section number of alternative plea option",
    "Name": "Name of accused person or parties",
    "Next Appearance": "Date, time, and room/purpose of next appearance",
    "No": "Number of item on the list",
    "Plea": "Plea entered (e.g., G = Guilty, NG = Not Guilty)",
    "Elec": "Election of trial mode",
    "Rm": "Courtroom number",
    "Rslt": "Appearance results / findings (e.g., IBJ = In Between Judgment / Adjourned, END = Concluded)",
    "Rsn": "Purpose/Reason of appearance (e.g., FA = First Appearance, PAR = Pre-Trial, FXD = Fix Date, SNT = Sentencing)",
    "Time": "Scheduled appearance time"
}

# Common process codes
PROCESS_CODES = {
    "AN": "Appearance Notice",
    "AWW": "Arrest Warrant Withdrawn",
    "DO": "Detention Order",
    "POA": "Promise to Appear",
    "ROD": "Release Order with Financial Condition",
    "RON": "Release Order without Financial Condition",
    "ROS": "Release Order with Surety",
    "ROW": "Release Order with Warrant",
    "SUM": "Summons",
    "UTP": "Undertaking to Appear",
    "WAR": "Warrant of Arrest",
    "PPA": "Personally Promising to Appear"
}

# Common result / disposition codes
RESULT_CODES = {
    "IBJ": "In Between Judgment / Adjourned",
    "END": "File Ended / Concluded",
    "SOP": "Stay of Proceedings",
    "PNI": "Plea of Not Guilty Entered / Information",
    "APG": "Admitted / Pled Guilty",
    "DIS": "Dismissed",
    "CNV": "Convicted",
    "ACQ": "Acquitted",
    "WDR": "Withdrawn"
}
