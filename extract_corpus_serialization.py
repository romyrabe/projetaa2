def extract_corpus(infile):
  """Extracts a file, gets rid of the POS tags, tokenizes it.
  Sentences are split into words based on " ". Nothing is done to uppercase letters or punctuation.
  Calibrated for the "L'Est républicain" corpus, cf README for the original download links.

  -> infile: string, path to the file
  <- tokenized_doc: list of lists of strings, a tokenized doc made of sentences made of words
  """
  tokenized_doc = []
  with open(infile, 'r', encoding = "utf-8-sig") as f:
    for line in f.readlines():
      sentence = []
      
      for word in line.split():
        sentence.append(word.split("/")[0])
      tokenized_doc.append(sentence)
  return tokenized_doc


"""For details about json files see https://www.codeflow.site/fr/article/python-json"""

def seralisation_data(data, title):
    """Serialize data in a json file (in desktop)
    -> data is the variable you want to serialize
    -> title must be a string : "title.json"
    <- Save a json file in desktop
    """

    with open(title, "w+") as file:
        json.dump(data,file)


def open_file(json_file):
    """ open_file open a json file and put content in variable data
    -> json file, json_file must a string "jsonfile.json"
    <- list of words
    """
    
    with open(json_file) as json_data:
        data = json.load(json_data)
        
    return data
