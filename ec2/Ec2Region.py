def GetLatestAmiId(region):
	region_ami = {
			"ap-northeast-1": "ami-ffc63b9e"
			, "ap-northeast-2": "ami-68a26806"
			, "ap-south-1": "ami-26f09a49"
			, "ap-southeast-1": "ami-6925f80a"
			, "ap-southeast-2": "ami-31b19a52"
			, "eu-central-1": "ami-e318f28c"
			, "eu-west-1": "ami-8fa6c1fc"
			, "sa-east-1": "ami-c6e97daa"
			, "us-east-1": "ami-6f8e0878"
			, "us-west-1": "ami-252b6d45"
			, "us-west-2": "ami-a58645c5"
			}

	return region_ami[region]


def All():
	return [
			"ap-northeast-1"
			, "ap-northeast-2"
			, "ap-south-1"
			, "ap-southeast-1"
			, "ap-southeast-2"
			, "eu-central-1"
			, "eu-west-1"
			, "sa-east-1"
			, "us-east-1"
			, "us-west-1"
			, "us-west-2"
			]
