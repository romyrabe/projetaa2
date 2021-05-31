"""Dans ce fichier, on se propose d'implémenter le modèle word2vec en version SkipGram avec sampling
négatif. Une fonction d'extraction de corpus est incluse.

Cette implémentation est très inspirée de :
- l'implémentation word2vec CBOW du TP8 du cours d'apprentissage automatique 2 de Marie Candito
- l'implémentation word2vec SkipGram de Xiaofei Sun (https://adoni.github.io/2017/11/08/word2vec-pytorch/)

TODO initialisation des embeddings, et voir si les scores passent bien à des valeurs entre 0 et 1
TODO évaluation
TODO argparse
TODO script pour tester les différents hyperparamètres
TODO sauvegarde des embeddings
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import argparse
import numpy as np
from collections import Counter
import random

torch.manual_seed(1)


def extract_corpus(infile):
  """Extracts the corpus, gets rid of the POS tags, tokenizes it.
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


class Word2Vec(nn.Module):
  """ Word2Vec model, SkipGram version with negative sampling.
  Creates word embeddings from a corpus using gradient descent.
  Use the train method to calculate the embeddings, TODO eval and save.

  The model learns:
  - one embedding for each of the vocab_size most frequent word tokens,
  - one embedding for unknown words (UNK),
  - 2*context_size embeddings for sentence boundaries (*D1*, *D2*, ... before the start of the sentence, *F1*, *F2*, ... after the end of it.).

  TODO later on, see which things we don't need past the initialisation, bc that's a lot of attributes
  Actually, some of them could be arguments of train()...?
  TODO also later on, see how long the code gets and if we want to split it up or not

  vocab_size          int, the number of real-word embeddings to learn
  context_size        int, the size of the context window on each side of the target word
                      if = 2, then for each word, four positive examples are created:
                      (x-2,x,+), (x-1,x,+), (x+1,x,+), (x+2,x,+)
  negative_examples   int, the number of negative examples per positive example
                      if = 2, then for each word, two negative examples are randomly created:
                      (r1, x, -), (r2, x, -)
  embedding_dim       int, the size of the word embeddings
  sampling            float, the sampling rate to calculate the negative example distribution probability
  number_epochs       int, the number of epochs to train for
  batch_size          int, the number of examples in a batch
  learning_rate       float, the learning rate step when training
  verbose             bool, verbose mode
  debug               bool, debug mode

  tokenized_doc         list of lists of strings, a tokenized doc made of sentences made of words,
                        as created by extract_corpus() for example
                        special words are not yet present
  indexed_doc           list of lists of ints, the same doc, indexes instead of tokens, special words in

  target_embeddings     Embeddings, the weights of the "hidden" layer for each target word,
                        and the final learned embeddings
  context_embeddings    Embeddings, the representation of each context word, the input for forward/predict

  occurence_counter     Counter object, occurence_counter["word"] = occurence_count(int)
  i2w                   list, index to word translator, i2w[index(int)] = "word"
  w2i                   dict, word to index translator, w2i["word"] = index(int)
  prob_dist             dict, prob_dist["word"] = probability of the word getting sampled
  examples              list of tuples, examples[(int)] = (context_word_id, target_word_id, pos|neg)
  optimizer             SGD, for the gradient descent in train
  """
  def __init__(self, tokenized_doc,
      context_size = 2,
      embedding_dim = 10,
      sampling = 0.75,
      negative_examples = 3,
      vocab_size = 10,
      number_epochs = 5,
      learning_rate = 0.05,
      batch_size = 5,
      verbose = True,
      debug = False):
    """ Initializes the model.
    TODO once we're done, put the default values to the best ones
    """
    super(Word2Vec, self).__init__()

    self.debug = debug
    self.verbose = verbose

    assert type(tokenized_doc) is list and type(tokenized_doc[0]) is list and \
      type(tokenized_doc[0][0] is str), "Problem with tokenized_doc."
    self.tokenized_doc = tokenized_doc
    if self.debug:
      print("Tokenized doc (first three sentences): "+str(self.tokenized_doc[0:3]))

    assert type(context_size) is int and context_size > 0, "Problem with context_size."
    self.context_size = context_size

    assert type(vocab_size) is int and vocab_size > 0, "Problem with vocab_size."
    self.vocab_size = vocab_size

    assert type(embedding_dim) is int and embedding_dim > 0, "Problem with embedding_dim."
    self.embedding_dim = embedding_dim

    assert type(sampling) is float and sampling > 0 and sampling < 1, "Problem with sampling."
    self.sampling = sampling

    assert type(np.negative) is int and negative_examples > 0, "Problem with negative_examples."
    self.negative_examples = negative_examples

    assert type(number_epochs) is int and number_epochs > 0, "Problem with number_epochs."
    self.number_epochs = number_epochs

    assert type(learning_rate) is float and learning_rate > 0, "Problem with learning_rate."
    self.learning_rate = learning_rate

    assert type(batch_size) is int and batch_size > 0, "Problem with batch_size."
    self.batch_size = batch_size

    if self.verbose:
      print("\nWord2Vec SKipGram model with negative sampling.")
      print("\nParameters:")
      print("context size = " + str(self.context_size))
      print("vocabulary size = " + str(self.vocab_size))
      print("embedding dimensions = " + str(self.embedding_dim))
      print("sampling rate = " + str(self.sampling))
      print("negative examples per positive example = " + str(self.negative_examples))
      print("number of epochs = " + str(self.number_epochs))
      print("learning rate = " + str(self.learning_rate))
      print("batch size = " + str(self.batch_size))

    self.target_embeddings = nn.Embedding(self.vocab_size, self.embedding_dim)
    self.context_embeddings = nn.Embedding(self.vocab_size, self.embedding_dim)
    self.__init_embed()
    if verbose: print("\nEmbeddings initialized.")

    self.occurence_counter = self.__get_occurence_counter()
    self.i2w = [token for token in self.occurence_counter]
    self.w2i = {w: i for i, w in enumerate(self.i2w)}
    self.indexed_doc = self.__get_indexed_doc()
    self.prob_dist =  self.__get_prob_dist()
    self.examples = self.__create_examples()
    self.optimizer = optim.SGD(self.parameters(), lr=self.learning_rate)
    if self.verbose: print("\nReady to train!")

  def __init_embed(self) :
    """Initializes the embeddinsg randomly (just like introduced in TP8)
    The target embeddings weights are between -0.5/self.embedding_dim and 0.5/self.embedding_dim while the context embeddings weights are zeroes."""

    initrange = 0.5/self.embedding_dim
    self.target_embeddings.weight.data.uniform_(-initrange,initrange)
    self.context_embeddings.weight.data.uniform_(-0,0)
    return

  def __get_occurence_counter(self):
    """Generates the occurence count with only the vocab_size most common words and the special words.
    Special words: UNK, *D1*, ...

    NOTE: We did consider using CountVectorizer but couldn't figure out how to deal with unknown words, which we do want to count too, because we need to create negative examples with them to create the other embeddings, and we need their distribution for that. TODO: double check, do we?

    NOTE: a Counter will give a count of 0 for an unknown word and a dict will not, which might be useful at some point, so we kept the Counter. TODO: double check at the end, does it help or not?

    NOTE: The occurence_counter need to be set before we replace rare words with UNK and add *D1* and all.
    That's because otherwise, a special word might not appear often enough to make the cut.
    We presumed that adding a few embeddings to the size wouldn't change much in terms of computation.
    However, it's absolutely possible to change it so that we keep vocab_size as the total number of
    embeddings learned, an only learn vocab_size - 2*self.context_size - 1 real word embeddings.
    """
    occurence_counter = Counter() # We want to count the number of occurences of each token, to only keep the VOCAB_SIZE most common ones.

    for sentence in self.tokenized_doc:
      occurence_counter.update(sentence) # cf https://docs.python.org/3/library/collections.html#collections.Counter

    if len(occurence_counter.keys()) - self.vocab_size > 0: # If there are tokens left over...
      #print("total:"+str(occurence_counter))
      UNK_counter = {token : count for (token, count)
          in occurence_counter.most_common()[self.vocab_size:]} # (it's actually a dict not a counter but shrug, doesn't matter for what we're doing with it)
      #print("unk: "+str(UNK_counter))
      occurence_counter.subtract(UNK_counter) # all those other tokens are deleted from the occurence count...
      #print("after subtract:"+str(occurence_counter))
      occurence_counter.update({"UNK": sum([UNK_counter[token] for token in UNK_counter])}) # and counted as occurences of UNK.

    occurence_counter.update({out_of_bounds : len(self.tokenized_doc) for out_of_bounds
        in ["*D"+str(i)+"*" for i in range(1,self.context_size+1)]
        + ["*F"+str(i)+"*" for i in range(1,self.context_size+1)]}) # We add one count of each out-of-bound special word per sentence.

    if self.verbose: print("\nOccurence counter created.")
    if self.debug: print("Occurence count: "+str(+occurence_counter))
    return +occurence_counter # "+" removes 0 or negative count elements.


  def __get_indexed_doc(self):
    """Generates an indexized version of the tokenized doc, adding out of bound and unknown special words.

    NOTE: If we wanted to adapt this model for other uses (for example, evaluating the 'likelihood' of a
    document), we'd probably need to adapt this method somehow, either for preprocessing input in main or
    for use in pred/forward. Since we don't care about that, it's set to private.
    """
    known_vocab_doc = []
    for sentence in self.tokenized_doc:
      sentence = ["*D"+str(i)+"*" for i in range(1,self.context_size+1)] + sentence + \
        ["*F"+str(i)+"*" for i in range(1,self.context_size+1)] # We add out-of-bound special words.
      for i, token in enumerate(sentence):
        if token not in self.w2i: # If we don't know a word...
          sentence[i] = "UNK" # we replace it by UNK.
      known_vocab_doc.append(sentence) # when I tried to change the tokenized doc directly, the changes got lost, sooo TODO Cécile : look into how referencing works in python again...

    # We switch to indexes instead of string tokens.
    indexed_doc = [[self.w2i[token] for token in sentence] for sentence in known_vocab_doc]

    if self.verbose: print("\nIndexed doc created.")
    if self.debug: print("Indexed doc: "+str(indexed_doc[0:3]))
    return indexed_doc


  def __get_prob_dist(self):
    """Generates the probability distribution of known words to get sampled as negative examples.
    """
    prob_dist = {}

    total_word_count = sum([self.occurence_counter[word]**self.sampling for word in self.occurence_counter])
    for word in self.occurence_counter:
      prob_dist[word] = (self.occurence_counter[word]**self.sampling)/total_word_count

    if self.verbose: print("\nProbability distribution created.")
    if self.debug: print("Probability distribution: "+str(prob_dist))
    return prob_dist


  def __create_examples(self):
    """Creates positive and negative examples using negative sampling.

    An example is a (target word, context word, gold tag) tuple.
    It is tagged 1 for positive (extracted from the corpus) and 0 for negative (randomly created).
    # TODO adapt that +/- to work with pred and/or loss
    """
    examples = []
    if self.debug: print("\nCreating examples...")

    for sentence in self.indexed_doc: # For each sentence...
      for target_i in range(self.context_size, len(sentence) - self.context_size): # For each word of the actual sentence...
        for context_i in range(target_i - self.context_size, target_i + self.context_size + 1): # For each word in the context window...
          if target_i is not context_i:
            examples.append((sentence[target_i], sentence[context_i], 1))
            if self.debug: print(self.i2w[sentence[target_i]]+","+self.i2w[sentence[context_i]]+",1")
            
        for sample in range(self.negative_examples): # Now, negative sampling! Using that probability distribution.
          random_token = np.random.choice(list(self.prob_dist.keys()), p=list(self.prob_dist.values()))
          if self.debug: print(self.i2w[sentence[target_i]]+","+random_token+",0")
          #TODO special words seem kind of overrepresented? to test
          examples.append((sentence[target_i], self.w2i[random_token], 0))
    
    if self.verbose: print("\nPositive and negative examples created.")
    return examples


  def forward(self, target_words, context_words):
    """ Calculates the probability of an example being found in the corpus, for all examples given.
    That is to say, the probability of a context word being found in the window of a context word.
    P(c|t) = sigmoid(c.t)

    We'll worry about the gold tags later, when we calculate the loss.
    P(¬c|t) = 1 - P(c|t)

    -> target_words: tensor, shape: (batch_size), line tensor of target word indexes
    -> context_words: tensor, shape: (batch_size), line tensor of context word indexes
    <- scores: tensor, shape: (batch_size), line tensor of scores
    """
    target_embeds = self.target_embeddings(target_words)
    context_embeds = self.context_embeddings(context_words)
    scores = torch.mul(target_embeds, context_embeds)
    scores = torch.sum(scores, dim=1)
    scores = F.logsigmoid(scores)

    if self.debug:
      print("\nForward propagation.")
      print("Targets: "+str(target_words))
      print("Contexts: "+str(context_words))
      print("Scores: "+str(scores))

    return scores


  def train(self):
    """ Executes gradient descent to learn the embeddings.
    This is where we switch to tensors: we need the examples to be in a list in order to shuffle them,
    but after that, for efficiency, we do all calculations using matrices.

    <- loss_over_epochs: list of ints, loss per epoch of training
    """
    if self.verbose: print("\nTraining...")
    loss_over_epochs = []

    for epoch in range(self.number_epochs):
      epoch_loss = 0
      random.shuffle(self.examples)
      batches = torch.split(torch.tensor(self.examples), self.batch_size)

      for batch in batches:
        target_words = batch[:,0]
        context_words = batch[:,1]
        gold_tags = batch[:,2]

        scores = self(target_words, context_words) # Forward propagation.
        batch_loss = -1 * torch.sum(torch.abs(scores - gold_tags))
        epoch_loss += batch_loss

        self.zero_grad() # Reinitialising model gradients.
        batch_loss.backward() # Back propagation, computing gradients.
        self.optimizer.step() # One step in gradient descent.

      if self.debug: print("Epoch "+str(epoch+1)+", loss = "+str(epoch_loss.item()))
      loss_over_epochs.append(epoch_loss.item())
    if self.verbose: print("Training done!")
    return loss_over_epochs



tokenized_doc = [["This","is","a", "test."], ["Test."]]

model = Word2Vec(tokenized_doc, verbose = True, debug = True)
loss_over_time = model.train()


#PARTIE MAIN
parser = argparse.ArgumentParser()
#Dans le terminal, on écrira "python3 init.py NOM_DU_FICHIER_CORPUS"
parser.add_argument('examples_file', default=None, help='Corpus utilisé pour la création d\'exemples d\'apprentissage pour les embeddings.')

#print(extract_corpus("mini_corpus.txt"))

