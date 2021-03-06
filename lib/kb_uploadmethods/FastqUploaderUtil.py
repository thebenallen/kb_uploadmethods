import os
import json
from ReadsUtils.ReadsUtilsClient import ReadsUtils
from ftp_service.ftp_serviceClient import ftp_service
from KBaseReport.KBaseReportClient import KBaseReport
from DataFileUtil.DataFileUtilClient import DataFileUtil
import uuid

def log(message):
    """Logging function, provides a hook to suppress or redirect log messages."""
    print(message)

class FastqUploaderUtil:

	def __init__(self, config):
		self.callback_url = config['SDK_CALLBACK_URL']
		self.token = config['KB_AUTH_TOKEN']
		self.scratch = config['scratch']

	def upload_fastq_file(self, params):
		"""
		upload_fastq_file: upload single-end fastq file or paired-end fastq files to workspace as read(s)
		                   source file can be either from user's staging area or web

		params: 
		fwd_staging_file_name: single-end fastq file name or forward/left paired-end fastq file name from user's staging area
		rev_staging_file_name: reverse/right paired-end fastq file name user's staging area
		sequencing_tech: sequencing technology
		name: output reads file name
		workspace_name: workspace name/ID that reads will be stored to
		download_type: download type for web source fastq file
		fwd_file_url: single-end fastq file URL or forward/left paired-end fastq file URL
		rev_file_url: reverse/right paired-end fastq file URL

		"""
		log('--->\nrunning FastqUploaderUtil.upload_fastq_file\nparams:\n%s' % json.dumps(params, indent=1))

		self.validate_upload_fastq_file_parameters(params)

		if 'fwd_staging_file_name' in params:
			# process single-end fastq file from user's staging area
			returnVal = self._upload_file_path(params)
		elif 'fwd_file_url' in params:
			# process single-end fastq file URL
			returnVal = self._upload_file_url(params)
		else:
			raise ValueError("Unexpected params: \n%s" % json.dumps(params, indent=1))

		return returnVal

	def generate_report(self, obj_refs, workspace_name):
		"""
		generate_report: generate summary report

		params: 
		obj_refs: generated workspace object references. (return of upload_fastq_file)
		workspace_name: workspace name/ID that reads will be stored to

		"""

		uuid_string = str(uuid.uuid4())
		obj_refs_list = obj_refs.split(',')

		dfu = DataFileUtil(self.callback_url)

		upload_message = 'Upload Finished\nUploaded Reads:\n'

		for obj_ref in obj_refs_list:
			get_objects_params = {
				'object_refs': [obj_ref],
				'ignore_errors': False
			}

			object_data = dfu.get_objects(get_objects_params)
			upload_message += "Reads Name: " + str(object_data.get('data')[0].get('info')[1]) + '\n'
			upload_message += "Reads Type: " + str(object_data.get('data')[0].get('info')[2]) + '\n'
			reads_info = object_data.get('data')[0].get('info')[-1]
			if isinstance(reads_info, dict):
				upload_message += "Reads Info: " + json.dumps(reads_info, indent=1)[1:-1] + '\n'

		report_params = { 
						'message': upload_message,
						'workspace_name' : workspace_name,
						'report_object_name' : 'kb_upload_mothods_report_' + uuid_string }

		kbase_report_client = KBaseReport(self.callback_url, token=self.token)
		output = kbase_report_client.create_extended_report(report_params)

		report_output = { 'report_name': output['name'], 'report_ref': output['ref'] }

		return report_output

	def validate_upload_fastq_file_parameters(self, params):
		"""
		validate_upload_fastq_file_parameters: validates params passed to upload_fastq_file method

		"""

		# check for required parameters
		for p in ['name', 'workspace_name']:
			if p not in params:
				raise ValueError('"' + p + '" parameter is required, but missing')	

		# check for invalidate both file path and file URL parameters
		upload_file_path = False
		upload_file_URL = False

		if 'fwd_staging_file_name' in params or 'rev_staging_file_name' in params:
			upload_file_path = True

		if 'fwd_file_url' in params or 'rev_file_url' in params:
			upload_file_URL = True

		if upload_file_path and upload_file_URL:
			raise ValueError('Cannot upload Reads for both file path and file URL')	

		# check for file path parameters
		if 'rev_staging_file_name' in params:
			self._validate_upload_file_path_availability(params["rev_staging_file_name"])
		elif 'fwd_staging_file_name' in params:
			self._validate_upload_file_path_availability(params["fwd_staging_file_name"])
		
		# check for file URL parameters
		if 'fwd_file_url' in params:
			self._validate_upload_file_URL_availability(params)

	def _validate_upload_file_path_availability(self, upload_file_name):
		"""
		_validate_upload_file_path_availability: validates file availability in user's staging area

		"""
		list = ftp_service(self.callback_url).list_files() #get available file list in user's staging area
		if upload_file_name.rpartition('/')[-1] not in list:
			raise ValueError("Target file: %s is NOT available. Available files: %s" % (upload_file_name.rpartition('/')[-1], ",".join(list)))

	def _validate_upload_file_URL_availability(self, params):
		"""
		_validate_upload_file_URL_availability: validates param URL format/connection 

		"""

		if 'download_type' not in params:
			raise ValueError("Download type parameter is required, but missing")

		# parse URL prefix
		if 'rev_file_url' in params:
			first_url_prefix = params['fwd_file_url'][:5].lower()
			second_url_prefix = params['rev_file_url'][:5].lower()
		elif 'fwd_file_url' in params and 'rev_file_url' not in params:
			url_prefix = params['fwd_file_url'][:5].lower()

		# check URL prefix
		if 'rev_file_url' in params:
			if params['download_type'] == 'Direct Download' and (first_url_prefix[:4] != 'http' or second_url_prefix[:4] != 'http'):
				raise ValueError("Download type and URL prefix do NOT match")
			elif params['download_type'] in ['DropBox', 'Google Drive']  and (first_url_prefix != 'https' or second_url_prefix != 'https'):
				raise ValueError("Download type and URL prefix do NOT match")
			elif params['download_type'] == 'FTP' and (first_url_prefix[:3] != 'ftp' or second_url_prefix[:3] != 'ftp'):
				raise ValueError("Download type and URL prefix do NOT match")
		elif 'fwd_file_url' in params and 'rev_file_url' not in params:
			if params['download_type'] == 'Direct Download' and url_prefix[:4] != 'http':
				raise ValueError("Download type and URL prefix do NOT match")
			elif params['download_type'] in ['DropBox', 'Google Drive'] and url_prefix != 'https':
				raise ValueError("Download type and URL prefix do NOT match")
			elif params['download_type'] == 'FTP' and url_prefix[:3] != 'ftp':
				raise ValueError("Download type and URL prefix do NOT match")

	def _upload_file_path(self, params):
		"""
		_upload_file_path: upload fastq file as reads from user's staging area

		params:
		fwd_staging_file_name: single-end fastq file name or forward/left paired-end fastq file name from user's staging area
		sequencing_tech: sequencing technology
		name: output reads file name
		workspace_name: workspace name/ID that reads will be stored to

		optional params:
		rev_staging_file_name: reverse/right paired-end fastq file name user's staging area
		single_genome: whether the reads are from a single genome or a metagenome
		insert_size_mean: mean (average) insert length
		insert_size_std_dev: standard deviation of insert lengths
		read_orientation_outward: whether reads in a pair point outward
		interleaved: whether reads is interleaved

		"""
		log ('---> running FastqUploaderUtil._upload_file_path')

		upload_file_params = params

		workspace_name_or_id = params.get('workspace_name')

		if str(workspace_name_or_id).isdigit():
			upload_file_params['wsid'] = int(workspace_name_or_id)
		else:
			upload_file_params['wsname'] = str(workspace_name_or_id)

		log('--->\nrunning ReadsUtils.upload_reads\nparams:\n%s' % json.dumps(upload_file_params, indent=1))
		ru = ReadsUtils(self.callback_url)
		result = ru.upload_reads(upload_file_params)

		return result

	def _upload_file_url(self, params):
		"""
		_upload_file_url: upload fastq file as reads from web

		params:
		download_type: download type for web source fastq file
		fwd_file_url: single-end fastq file URL or forward/left paired-end fastq file URL
		sequencing_tech: sequencing technology
		name: output reads file name
		workspace_name: workspace name/ID that reads will be stored to

		optional params:
		rev_file_url: reverse/right paired-end fastq file URL
		single_genome: whether the reads are from a single genome or a metagenome
		insert_size_mean: mean (average) insert length
		insert_size_std_dev: standard deviation of insert lengths
		read_orientation_outward: whether reads in a pair point outward
		interleaved: whether reads is interleaved
		
		"""
		log ('---> running FastqUploaderUtil._upload_file_url')

		upload_file_params = params

		workspace_name_or_id = params.get('workspace_name')

		if str(workspace_name_or_id).isdigit():
			upload_file_params['wsid'] = int(workspace_name_or_id)
		else:
			upload_file_params['wsname'] = str(workspace_name_or_id)

		log('--->\nrunning ReadsUtils.upload_reads\nparams:\n%s' % json.dumps(upload_file_params, indent=1))
		ru = ReadsUtils(self.callback_url)
		result = ru.upload_reads(upload_file_params)

		return result

