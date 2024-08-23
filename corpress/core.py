# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['get_api_url', 'get_json', 'create_corpus', 'result_reporting', 'corpress']

# %% ../nbs/00_core.ipynb 3
import requests
from bs4 import BeautifulSoup
import logging
import time
import os
import glob
import json
import html
import pandas as pd
import csv
from slugify import slugify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# %% ../nbs/00_core.ipynb 6
def get_api_url(url: str, # the URL of the WordPress website 
                endpoint_type: str = 'posts', # posts or pages
                headers: dict = None, # optional headers for requests
                ) -> str|None: # None if no endpoint detected, otherwise returns the endpoint URL
    """Queries a URL to get the REST API route for the endpoint type provided. """

    if not headers:
        headers = {}

    endpoint_url = None
        
    match endpoint_type:
        case 'posts':
            endpoint = 'wp/v2/posts'
        case 'pages':
            endpoint = 'wp/v2/pages'
        case _:
            logging.error('The endpoint must be posts or pages.')
            return None

    if url.endswith(endpoint):
        logging.info(f'URL {endpoint_url} appears to be REST API {endpoint_type} route')
        endpoint_url = url
    else:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            try:
                json_data = response.json()
                if 'routes' in json_data:
                    endpoint_url = json_data['routes']['/' + endpoint]['_links']['self'][0]['href']
                    logging.info('URL is REST API endpoint')
                    logging.info(f'Extracted {endpoint_type} route {endpoint_url}')
            except (requests.JSONDecodeError, KeyError) as e:
                soup = BeautifulSoup(response.content, 'lxml')
                link = soup.find('link', rel="https://api.w.org/")
                if link:
                    if link['href'].endswith('/'):
                        endpoint_url = link['href'] + endpoint
                    else:
                        endpoint_url = link['href'] + '/' + endpoint
                    logging.info('Found REST API endpoint link')
                    logging.info(f'Setting {endpoint_type} route {endpoint_url}')
                else:
                    if url.endswith('/'):
                        endpoint_url = url + 'wp-json/' + endpoint
                    else:
                        endpoint_url = url + '/wp-json/' + endpoint
                    logging.info('No REST API endpoint link in markup')
                    logging.info(f'Guessing {endpoint_type} route based on URL {endpoint_url}')
        except requests.HTTPError as e:
            logging.error(f'{url} returned status code {response.status_code}')
            
    return endpoint_url


# %% ../nbs/00_core.ipynb 9
def get_json(endpoint_url: str, # the URL of the WordPress REST API endpoint
             endpoint_type: str = 'posts', # the type of data to download
             headers: dict = None, # optional headers for requests
             params: dict = None, # optional parameters to pass to the API
             json_save_path: str = None, # path to save the JSON data 
             seconds_between_requests: int = 5, # number of seconds to wait between requests, must be at least 1
             max_pages: int = None # maximum number of pages to download
            ) -> bool: # True if successful, False otherwise 
    """Download and save JSON data from a specific REST API endpoint. """

    if not endpoint_url:
        logging.error('No endpoint URL provided')
        return False
    
    if seconds_between_requests < 1:
        seconds_between_requests = 1
        logging.warning('Setting minimum seconds between requests to 1 as value provided is less than 1')
    
    if not params:
        params = {}
    
    if not headers:
        headers = {}

    if not json_save_path:
        logging.error('No path provided to save JSON data')
        return False

    if not os.path.exists(json_save_path):
        os.makedirs(json_save_path)
        logging.info(f'Created JSON save path: {json_save_path}')
    else:
        logging.info(f'Using JSON save path: {json_save_path}')

    match endpoint_type:
        case 'posts':
            pass
        case 'pages':
            pass
        case _:
            logging.error('The endpoint must be posts or pages.')
            return False

    if max_pages is not None:
        logging.info(f'Max pages to retrieve from API is set: {max_pages}')

    has_more = True
    page = 1
    total_pages = False
    consecutive_errors = 0

    while has_more == True:
        try:
            params['page'] = page
            r = requests.get(endpoint_url, params=params, headers=headers)
            
            logging.info(f'Downloading {r.url}')
            r.raise_for_status()

            if total_pages == False:
                total_pages = int(r.headers['X-WP-TotalPages'])
                logging.info(f'Total pages to retrieve is {total_pages}')
                digits = len(str(total_pages))

            filename = os.path.join(json_save_path, f'{endpoint_type}-{page:0{digits}}.json')

            with open(filename, 'wb') as f:
                f.write(r.content)
                #logging.info(f'Saved to {filename}')

            page += 1
            if page > total_pages:
                has_more = False

            if max_pages is not None and page > max_pages:
                has_more = False

            consecutive_errors = 0
        except requests.HTTPError as e:
            logging.error(f'Error downloading page {page} from {endpoint_url}')
            logging.error(f'Status code: {r.status_code}')
            if page == 1:
                logging.error('It appears that this website does not provide access to the REST API. Exiting.')
            else:
                logging.error('Exiting based on status code error. If this is a 403 or 400, it may be that the website is refusing repeated access to their REST API.')
            return False
        # exception for Timeout or ConnectionError
        except (requests.Timeout, requests.ConnectionError) as e:
            logging.error(f'Error downloading page {page} ({e}) from {endpoint_url}')
            consecutive_errors += 1
            if consecutive_errors > 3:
                return False

        time.sleep(seconds_between_requests)

    return True



# %% ../nbs/00_core.ipynb 11
def create_corpus(corpus_format: str = 'txt', # format of the corpus files, txt or csv
                  json_save_path: str = None, # path to JSON data 
                  corpus_save_path: str = None, # path to save corpus in txt format
                  csv_save_file: str = None, # path to CSV file to output corpus in CSV format (or metadata if txt corpus)
                  include_title_in_text: bool = True # include the title in the text file 
                 ) -> bool: # True if successful, False if there are errors parsing the JSON 
    """Create a corpus from downloaded JSON data in txt or csv format. """

    match corpus_format:
        case 'txt':
            columns = ['date', 'datetime', 'type', 'id', 'title', 'link', 'filename']
            csv_file_type = 'metadata'
        case 'csv':
            columns = ['date', 'datetime', 'type', 'id', 'title', 'link', 'text']
            csv_file_type = 'corpus'
        case _:
            logging.error('Corpus format must be txt or csv')
            return False

    logging.info(f'Creating corpus in {corpus_format} format')

    if not json_save_path:
        logging.error('No path provided to json data')
        return False
    else:
        if not os.path.exists(json_save_path):
            logging.error('Path to JSON data does not exist')
            return False
    
    if corpus_format == 'txt':
        if not corpus_save_path:
            logging.error('No corpus save path provided')
            return False
        if not os.path.exists(corpus_save_path):
            os.makedirs(corpus_save_path)
            logging.info(f'Created corpus save path: {corpus_save_path}')
        else:
            logging.info(f'Using corpus save path: {corpus_save_path}')

    if corpus_format == 'csv':
        if not csv_save_file:
            logging.error('No path provided to save CSV corpus')
            return False
    
    if csv_save_file:
        csv_save_path = os.path.dirname(csv_save_file)
        if not os.path.exists(os.path.dirname(csv_save_path)):
            os.makedirs(os.path.dirname(csv_save_path))
            logging.info(f'Created path to save CSV corpus: {os.path.dirname(csv_save_path)}')

    try:
        # if csv_save_path is provided (regardless of format) create it and write first row
        if csv_save_file:
            logging.info(f'Creating CSV file for {csv_file_type}: {csv_save_file}')
            fw = open(csv_save_file, 'w', encoding='utf-8')
            writer = csv.writer(fw)
            writer.writerow(columns)
 
        file_list = glob.glob(json_save_path + '/*.json')
        for file in file_list:
            with open(file, 'r', encoding='utf-8') as f:
                logging.info(f"Processing JSON: {os.path.basename(file)}")
                data = json.load(f)
                for article in data:
                    title = html.unescape(article['title']['rendered'])
                    filename = f"{article['date'][0:10]}-{article['type']}-{article['id']}-{slugify(title, max_length=100)}.txt"
                    #logging.info(f"Processing {article['type']}: {title}")
                    soup = BeautifulSoup(article['content']['rendered'], 'lxml')
                    content = soup.get_text().strip()

                    if csv_save_file:
                        if corpus_format == 'csv':
                            writer.writerow([article['date'][0:10], article['date'], article['type'], article['id'], article['link'], title, content])
                        else:
                            writer.writerow([article['date'][0:10], article['date'], article['type'], article['id'], article['link'], title, filename])
                        
                    if corpus_format == 'txt':
                        #logging.info(f'Saving corpus file {filename}')
                        with open(corpus_save_path + filename, 'w', encoding='utf-8') as txtfile:
                            if include_title_in_text:
                                txtfile.write(title + '\n\n')
                            txtfile.write(content)

    except json.JSONDecodeError as e:
        logging.error(f'Exception (JSONDecodeError) - error decoding JSON file: {os.path.basename(file)}')
        return False
    except KeyError as e:
        logging.error(f'Exception (KeyError) - indicating unexpected JSON file content: {os.path.basename(file)}')
        return False
    except Exception as e:
        logging.error(f'Exception - {e} - exiting by raising error ...')
        raise
    
    return True
   


# %% ../nbs/00_core.ipynb 14
def result_reporting(result: dict, # the result dictionary
                     output: bool = True # output the results
                     ) -> dict: # returns the result dictionary
    """Outputs the results of the corpress process"""

    # output dataframe
    df = pd.DataFrame(result.items(), columns=['Key', 'Value'])
    
    try: # if in a Jupyter notebook
        display(df)
    except NameError:
        print(df)

    return result
    

# %% ../nbs/00_core.ipynb 15
def corpress(url: str, # the URL of the WordPress website 
            endpoint_type: str = 'posts', # posts or pages
            headers: dict = None, # optional headers for requests
            params: dict = None, # optional parameters to pass to the API
            corpus_format: str = 'txt', # format of the corpus files, txt or csv
            json_save_path: str = None, # path to save the JSON data 
            corpus_save_path: str = None, # path to save the corpus in txt format
            csv_save_file: str = None, # path to CSV file to output corpus in CSV format (or metadata if txt corpus)
            seconds_between_requests: int = 5, # number of seconds to wait between requests
            max_pages: int = None, # maximum number of pages to download
            include_title_in_text: bool = True, # option to include the title in the text file 
            output: bool = True # option to output the results of the process
            ) -> dict: # dictionary with results of each stage of the process and the number of texts in the corpus
    """Retrieve data from the REST API and create a corpus."""
    
    result = {
        'url': url,
        'endpoint_url': None,
        'headers': headers,
        'params': None,
        'get_api_url': False,
        'get_json': False,
        'create_corpus': False,
        'corpus_format': corpus_format,
        'corpus_save_path': corpus_save_path,
        'csv_save_file': csv_save_file,
        'corpus_texts_count': 0
    }

    # get the endpoint_url
    endpoint_url = get_api_url(url, endpoint_type, headers)
    
    if not endpoint_url:
        logging.error('No endpoint URL detected. Exiting.')
        return result_reporting(result, output)
    else:
        result['get_api_url'] = True
        result['endpoint_url'] = endpoint_url

    # if params is a dict
    if isinstance(params, dict):
        result['params'] = params.copy()
    
    # download the data
    get_json_result = get_json(endpoint_url, endpoint_type, headers, params, json_save_path, seconds_between_requests, max_pages)

    if get_json_result == False:
        logging.error('Error downloading data. Exiting.')
        return result_reporting(result, output)
    else:
        result['get_json'] = True

    # create the corpus
    create_corpus_result = create_corpus(corpus_format, json_save_path, corpus_save_path, csv_save_file, include_title_in_text)

    if create_corpus_result == False:
        logging.error('Error creating corpus')
        return result_reporting(result, output)
    else:
        result['create_corpus'] = True

    if corpus_format == 'txt':
        result['corpus_texts_count'] = len(os.listdir(corpus_save_path))
    elif corpus_format == 'csv':
        result['corpus_texts_count'] = len(pd.read_csv(csv_save_file))

    return result_reporting(result, output)
