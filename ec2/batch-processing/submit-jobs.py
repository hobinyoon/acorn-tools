#!/usr/bin/env python

import boto3
import botocore
import json
import os
import pprint
import sys

sys.path.insert(0, "%s/../../util/python" % os.path.dirname(__file__))
import Cons

sys.path.insert(0, "%s/.." % os.path.dirname(__file__))
import Ec2Region


sqs_region = "us-east-1"
q_name_jr = "acorn-jobs-requested"
msg_body = "acorn-exp-req"

def main(argv):
	bc = boto3.client("sqs", region_name = sqs_region)
	sqs = boto3.resource("sqs", region_name = sqs_region)
	q = GetQ(bc, sqs)

	SingleDevNode(q)

	#ByYoutubeWorkloadOfDifferentSizes(q)

	#ByRepModels(q)

	# To dig why some requests are running behind
	#MeasureClientOverhead(q)

	# Measure xDC traffic of object replication and metadata
	#MeasureMetadataXdcTraffic(q)


# Get the queue. Create one if not exists.
def GetQ(bc, sqs):
	with Cons.MT("Getting the queue ..."):
		queue = sqs.get_queue_by_name(
				QueueName = q_name_jr,
				# QueueOwnerAWSAccountId='string'
				)
		#Cons.P(pprint.pformat(vars(queue), indent=2))
		#{ '_url': 'https://queue.amazonaws.com/998754746880/acorn-exps',
		#		  'meta': ResourceMeta('sqs', identifiers=[u'url'])}
		return queue


def SingleDevNode(q):
	req_attrs = {
			"init_script": "acorn-dev"
			, "region_spot_req": {
				"us-east-1": {"inst_type": "r3.xlarge", "max_price": 1.0}
				}
			}
	_EnqReq(q, req_attrs)


# Pricing can be specified per datacenter too later when needed.
# TODO
_region_inst_type = {
		"ap-northeast-1": "r3.xlarge"
		, "ap-northeast-2": "r3.xlarge"
		, "ap-south-1": "r3.xlarge"
		, "ap-southeast-1": "r3.xlarge"
		, "ap-southeast-2": "r3.xlarge"

		# r3.xlarge is oversubscribed and expensive. strange.
		, "eu-central-1": "r3.2xlarge"

		, "eu-west-1": "r3.xlarge"

		# Sao Paulo doesn't have r3.xlarge
		, "sa-east-1": "c3.2xlarge"

		, "us-east-1": "r3.xlarge"
		, "us-west-1": "r3.xlarge"
		, "us-west-2": "r3.xlarge"
		}


def ByYoutubeWorkloadOfDifferentSizes(q):
	req_attrs = {
			"init_script": "acorn-server"
			, "region_inst_type": _region_inst_type
			, "max_price": 1.0

			# Partial replication metadata is exchanged
			, "acorn-youtube.replication_type": "partial"

			, "acorn-youtube.fn_youtube_reqs": "tweets-010"

			# Default is 10240
			#, "acorn-youtube.youtube_extra_data_size": "10240"

			# Default is -1 (request all)
			#, "acorn-youtube.max_requests": "-1"

			# Default is 35 mins, 2100 secs.
			#, "acorn-youtube.simulation_time_dur_in_ms": "2100000"

			# Default is true, true
			#, "acorn_options.use_attr_user": "true"
			#, "acorn_options.use_attr_topic": "true"
			}
	#for wl in ["tweets-010", "tweets-017", "tweets-054", "tweets-076", "tweets-100"]:
	for wl in ["tweets-017"]:
		req_attrs["acorn-youtube.fn_youtube_reqs"] = wl
		_EnqReq(q, req_attrs)

	# Full replication, of course without any acorn metadata exchange
	req_attrs["acorn-youtube.replication_type"] = "full"
	req_attrs["acorn_options.use_attr_user"] = "false"
	req_attrs["acorn_options.use_attr_topic"] = "false"

	#for wl in ["tweets-010", "tweets-017", "tweets-054", "tweets-076", "tweets-100"]:
#	for wl in ["tweets-010", "tweets-017"]:
#		req_attrs["acorn-youtube.fn_youtube_reqs"] = wl
#		_EnqReq(q, req_attrs)


def ByRepModels(q):
	# UT
	req_attrs = {
			"init_script": "acorn-server"
			, "regions": Ec2Region.All()

			# Partial replication metadata is exchanged
			, "acorn-youtube.replication_type": "partial"

			, "acorn-youtube.fn_youtube_reqs": "tweets-010"

			# Default is 10240
			#, "acorn-youtube.youtube_extra_data_size": "10240"

			# Default is -1 (request all)
			#, "acorn-youtube.max_requests": "-1"
			, "acorn-youtube.max_requests": "100000"

			# Default is 1800000
			#, "acorn-youtube.simulation_time_dur_in_ms": "1800000"
			, "acorn-youtube.simulation_time_dur_in_ms": "10000"

			# Default is true, true
			, "acorn_options.use_attr_user": "true"
			, "acorn_options.use_attr_topic": "true"
			}
	_EnqReq(q, req_attrs)

#	# T
#	req_attrs["acorn_options.use_attr_user"] = "false"
#	req_attrs["acorn_options.use_attr_topic"] = "true"
#	_EnqReq(q, req_attrs)
#
#	# U
#	req_attrs["acorn_options.use_attr_user"] = "true"
#	req_attrs["acorn_options.use_attr_topic"] = "false"
#	_EnqReq(q, req_attrs)
#
#	# NA
#	req_attrs["acorn_options.use_attr_user"] = "false"
#	req_attrs["acorn_options.use_attr_topic"] = "false"
#	_EnqReq(q, req_attrs)
#
#	# Full
#	req_attrs["acorn-youtube.replication_type"] = "full"
#	req_attrs["acorn_options.use_attr_user"] = "false"
#	req_attrs["acorn_options.use_attr_topic"] = "false"
#	_EnqReq(q, req_attrs)


def MeasureClientOverhead(q):
	# Maximum 5%. Most of the time negligible.
	req_attrs = {
			# Swap the coordinates of us-east-1 and eu-west-1 to see how much
			# overhead is there in eu-west-1
			"regions": ["us-east-1"]
			, "acorn-youtube.fn_youtube_reqs": "tweets-100"
			, "acorn-youtube.youtube_extra_data_size": "512"

			# Request all
			, "acorn-youtube.max_requests": "-1"

			, "acorn-youtube.simulation_time_dur_in_ms": "1800000"
			}
	_EnqReq(q, req_attrs)


def MeasureMetadataXdcTraffic(q):
	Cons.P("regions: %s" % ",".join(Ec2Region.All()))

	req_attrs = {
			"regions": Ec2Region.All()

			# Partial replication metadata is exchanged
			, "acorn-youtube.replication_type": "partial"

			# Objects are fully replicated
			, "acorn_options.full_replication": "true"

			, "acorn-youtube.fn_youtube_reqs": "tweets-010"

			, "acorn-youtube.youtube_extra_data_size": "10240"

			# Request all
			, "acorn-youtube.max_requests": "-1"

			, "acorn-youtube.simulation_time_dur_in_ms": "1800000"
			}
	_EnqReq(q, req_attrs)

	# Full replication, of course without any acorn metadata exchange
	req_attrs["acorn-youtube.replication_type"] = "full"
	req_attrs["acorn_options.use_attr_user"] = "false"
	req_attrs["acorn_options.use_attr_topic"] = "false"
	_EnqReq(q, req_attrs)


def MeasureMetadataXdcTrafficSmallScale(q):
	Cons.P("regions: %s" % ",".join(Ec2Region.All()))

	req_attrs = {
			"regions": Ec2Region.All()

			# Partial replication metadata is exchanged
			, "acorn-youtube.replication_type": "partial"

			# Objects are fully replicated
			, "acorn_options.full_replication": "true"

			, "acorn-youtube.fn_youtube_reqs": "tweets-010"
			, "acorn-youtube.max_requests": "5000"
			, "acorn-youtube.simulation_time_dur_in_ms": "10000"
			}
	_EnqReq(q, req_attrs)

	# Full replication, of course without any acorn metadata exchange
	req_attrs["acorn-youtube.replication_type"] = "full"
	req_attrs["acorn_options.use_attr_user"] = "false"
	req_attrs["acorn_options.use_attr_topic"] = "false"
	_EnqReq(q, req_attrs)


def _EnqReq(q, attrs):
	with Cons.MT("Enq a request: "):
		attrs = attrs.copy()
		Cons.P(pprint.pformat(attrs))

		jc_params = {}
		for k in attrs.keys():
			if k in ["init_script", "region_spot_req"]:
				jc_params[k] = attrs[k]
				del attrs[k]
		#Cons.P(json.dumps(jc_params))

		msg_attrs = {}
		for k, v in attrs.iteritems():
			msg_attrs[k] = {"StringValue": v, "DataType": "String"}
		msg_attrs["job_controller_params"] = {"StringValue": json.dumps(jc_params), "DataType": "String"}

		q.send_message(MessageBody=msg_body, MessageAttributes=msg_attrs)


if __name__ == "__main__":
	sys.exit(main(sys.argv))
