import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Optional
import json

import httpx
import questionary
from tqdm.auto import tqdm
from loguru import logger


class Client:
    def __init__(
            self,
            *,
            save_path: Optional[str] = "./output/",
            wait_time: Optional[float] = 1,
            max_retries: Optional[int] = 5,
            manifest_name: Optional[str] = "manifest.list",
            download_workers: Optional[int] = 5
    ):
        logger.remove()
        logger.add(
            sys.stdout,
            colorize=True,
            format="<cyan>[{time:HH:mm:ss:SSS}]</cyan> "
                   "<level>[{function}/{level}]</level>: "
                   "<level>{message}</level>"
        )
        self._save_folder = os.path.abspath(save_path)
        self._wait_time = wait_time
        self._max_retries = max_retries
        self._save_texts = True
        self._default_manifest_format = r"{path}|{text}"
        self._manifest_file_instance = None
        self._manifest_name = manifest_name
        self._download_workers = download_workers if download_workers and download_workers > 0 else 1
        self._cache_dir = os.path.join(self._save_folder, ".cache")
        self._cache_ttl_seconds = 30 * 24 * 60 * 60
        self._client = httpx.Client(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            http2=True,
            headers={"User-Agent": "FindUrVoicesPJSK/v1"},
        )
        self._manifest_lock = Lock()
        self._cache_lock = Lock()
        os.makedirs(self._cache_dir, exist_ok=True)
        logger.info(f"The files will save in {os.path.join(self._save_folder, 'dataset_[ID]')}")
        self._download_data()

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response | None:
        retries = 0
        while retries < self._max_retries:
            try:
                response = self._client.get(url, params=params)
                return response
            except Exception as e:
                retries += 1
                if retries < self._max_retries:
                    logger.warning(f"Retrying on get file, times: {retries}, exception: {e}")
                    time.sleep(self._wait_time)
                else:
                    raise httpx.ConnectError
        return None

    def _cache_path(self, key: str) -> str:
        return os.path.join(self._cache_dir, f"{key}.json")

    def _load_cache(self, key: str) -> Optional[dict]:
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > self._cache_ttl_seconds:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache for {key}: {e}")
            return None

    def _save_cache(self, key: str, data: dict) -> None:
        path = self._cache_path(key)
        with self._cache_lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as e:
                logger.warning(f"Failed to write cache for {key}: {e}")

    def _download_data(self) -> None:
        endpoints = {
            "_characters": "https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json",
            "_musics": "https://sekai-world.github.io/sekai-master-db-diff/musics.json",
            "_music_vocals": "https://sekai-world.github.io/sekai-master-db-diff/musicVocals.json",
            "_character_profiles": "https://sekai-world.github.io/sekai-master-db-diff/characterProfiles.json",
            "_character_2ds": "https://sekai-world.github.io/sekai-master-db-diff/character2ds.json",
            "_cards": "https://sekai-world.github.io/sekai-master-db-diff/cards.json",
            "_cards_episodes": "https://sekai-world.github.io/sekai-master-db-diff/cardEpisodes.json",
        }

        def fetch(key: str, url: str):
            cache_hit = self._load_cache(key)
            if cache_hit is not None:
                logger.info(f"Using cached {key.replace('_', ' ').strip()} data")
                return cache_hit

            logger.info(f"Downloading {key.replace('_', ' ').strip()} data ...")
            response = self._get(url)
            if not response:
                logger.warning(f"Failed to download {key}, falling back to cache if available.")
                return cache_hit if cache_hit is not None else {}

            data = response.json()
            self._save_cache(key, data)
            return data

        with ThreadPoolExecutor(max_workers=min(8, len(endpoints))) as executor:
            future_to_key = {
                executor.submit(fetch, key, url): key for key, url in endpoints.items()
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                setattr(self, key, future.result())
        self._build_indexes()

    def _build_indexes(self) -> None:
        self._musics_by_id = {music["id"]: music for music in self._musics}
        self._character_2d_ids_by_character = defaultdict(list)
        for character_2d in self._character_2ds:
            self._character_2d_ids_by_character[character_2d["characterId"]].append(character_2d["id"])
        self._profiles_by_character = {profile["characterId"]: profile for profile in self._character_profiles}
        self._cards_by_character = defaultdict(list)
        for card in self._cards:
            self._cards_by_character[card["characterId"]].append(card)
        self._scenario_ids_by_assetbundle = defaultdict(list)
        for episode in self._cards_episodes:
            self._scenario_ids_by_assetbundle[episode["assetbundleName"]].append(episode["scenarioId"])

    def select_character(self) -> int:
        choices = []

        for i, character in enumerate(self._characters):
            choices.append(
                questionary.Choice(
                    f"{character['firstName'] if 'firstName' in character else ''}{character['givenName']}",
                    i
                )
            )

        selected = self._characters[questionary.select(
            "Please select the character: ",
            choices
        ).ask()]

        return selected['id']

    def _check_dataset_folder(self, character_id: int) -> str:
        save_path = os.path.join(self._save_folder, f"dataset_{character_id}")

        if not os.path.exists(save_path):
            os.makedirs(save_path, exist_ok=True)

        return save_path

    def _serialize_manifest_format(self, **kwargs) -> str:
        result = self._default_manifest_format
        for key, item in kwargs.items():
            result = result.replace("{" + key + "}", item)
        return result

    def _write_manifest_line(self, save_path: str, file_path: str, text: str) -> None:
        if not self._save_texts:
            return

        with self._manifest_lock:
            if not self._manifest_file_instance:
                self._manifest_file_instance = open(
                    os.path.join(save_path, self._manifest_name),
                    "a+",
                    encoding="utf-8",
                    buffering=1
                )

            line = self._serialize_manifest_format(
                path=file_path,
                text=text
            ) + "\n"

            self._manifest_file_instance.write(line)

    def _progress_log(self, message: str) -> None:
        tqdm.write(message)

    def _fetch_and_save(self, url: str, file_path: str) -> bool:
        try:
            response = self._get(url)
            if not response:
                logger.warning("Get status code 404, perhaps the resource is not exist.")
                return False

            content = response.content
            if not content:
                logger.warning("Empty response content, perhaps the resource is not exist.")
                return False

            with open(file_path, "wb") as f:
                f.write(content)

            return True
        except Exception as e:
            logger.warning(f"Download failed for {url}: {e}")
            return False
        finally:
            if self._wait_time:
                time.sleep(self._wait_time)

    def download_solo_songs(self, character_id: int) -> None:
        # Code S000
        save_path = self._check_dataset_folder(character_id)
        tasks = []
        index = 1
        for music in self._music_vocals:
            singers = [x['characterId'] for x in music['characters'] if x['characterType'] == 'game_character']

            if not len(singers) == 1:
                continue

            if not character_id in singers:
                continue

            music_detail = self._musics_by_id.get(music["musicId"])
            if not music_detail:
                continue

            music_title = music_detail['title']
            music_asset_bundle_name = music['assetbundleName']
            file_name = f"S{str(index).zfill(3)}.wav"

            logger.info(f"Downloading {music_title} | {music_asset_bundle_name} -> {file_name} ...")

            file_path = os.path.join(save_path, file_name)
            url = (
                "https://storage.sekai.best"
                f"/sekai-jp-assets/music/long/{music_asset_bundle_name}/{music_asset_bundle_name}.wav"
            )
            tasks.append((url, file_path))

            index += 1

        if not tasks:
            return

        with ThreadPoolExecutor(max_workers=self._download_workers) as executor:
            futures = [executor.submit(self._fetch_and_save, url, file_path) for url, file_path in tasks]
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Solo songs",
                unit="file",
                position=0,
                leave=True
            ):
                if not future.result():
                    return

    def _parse_and_download_asset(
            self,
            asset: dict,
            scenario_id: str,
            save_path: str,
            select_character_2d_ids: list,
            base_url: str,
            file_name_len: int,
            prefix: str,
            index: int,
            count: Optional[int] = None,
            overall_bar: Optional[tqdm] = None,
    ) -> int:
        tasks = []
        talk_data = asset.get('TalkData', [])
        for data in talk_data:
            speakers = [x['Character2dId'] for x in data['TalkCharacters']]
            if not len(speakers) == 1:
                continue
            if not len([x for x in speakers if x not in select_character_2d_ids]) == 0:
                continue

            for voice in data['Voices']:
                if voice['Character2dId'] not in select_character_2d_ids:
                    continue

                url = f"{base_url}/{scenario_id}/{voice['VoiceId']}.wav"
                file_name = f"{prefix}{str(index).zfill(file_name_len)}.wav"
                cleaned_body = data['Body'].replace("\n", "")
                self._progress_log(f"Downloading {cleaned_body} -> {file_name} ...")

                file_path = os.path.join(save_path, file_name)
                tasks.append((url, file_path, cleaned_body))

                index += 1

                if count and len(tasks) >= count:
                    break
            if count and len(tasks) >= count:
                break

        if not tasks:
            return index

        if count:
            tasks = tasks[:count]

        def _run_download(target_bar: Optional[tqdm]) -> int:
            with ThreadPoolExecutor(max_workers=self._download_workers) as executor:
                futures = [
                    executor.submit(
                        self._download_voice_with_manifest,
                        url,
                        file_path,
                        cleaned_body,
                        save_path
                    )
                    for url, file_path, cleaned_body in tasks
                ]

                for future in as_completed(futures):
                    if not future.result():
                        return -1
                    if target_bar:
                        target_bar.update(1)
            return index

        if overall_bar:
            result = _run_download(overall_bar)
            return result

        with tqdm(
            total=len(tasks),
            desc=f"{prefix} voices",
            position=0,
            leave=True,
            unit="file",
            dynamic_ncols=True
        ) as local_bar:
            result = _run_download(local_bar)

        return result

        return index

    def download_character_profile_voices(self, character_id: int) -> None:
        # Code P000
        save_path = self._check_dataset_folder(character_id)

        profile = self._profiles_by_character.get(character_id)
        if not profile:
            logger.warning(f"No profile found for character id: {character_id}")
            return

        scenario_id = profile['scenarioId']
        logger.info(f"Character scenario_id: {scenario_id}")

        select_character_2d_ids = self._character_2d_ids_by_character.get(character_id, [])
        logger.info(f"Character 2d ids: {', '.join([str(x) for x in select_character_2d_ids])}")

        logger.info("Downloading profile voices asset file...")
        profile_voice_asset = self._get(
            f"https://storage.sekai.best/sekai-jp-assets/scenario/profile/{scenario_id}.asset"
        ).json()
        logger.info(f"Profile voice asset name: {profile_voice_asset['m_Name']}")
        self._parse_and_download_asset(
            profile_voice_asset,
            scenario_id,
            save_path,
            select_character_2d_ids,
            "https://storage.sekai.best/sekai-jp-assets/sound/scenario/voice",
            3,
            "P",
            1
        )

    def download_character_cards_voices(self, character_id: int, card_voices_count: int) -> None:
        # Code C0000
        save_path = self._check_dataset_folder(character_id)

        character_cards = self._cards_by_character.get(character_id, [])
        logger.info(f"Character card counts: {len(character_cards)}")

        select_character_2d_ids = self._character_2d_ids_by_character.get(character_id, [])
        logger.info(f"Character 2d ids: {', '.join([str(x) for x in select_character_2d_ids])}")

        index = 1

        remaining_target = card_voices_count
        with tqdm(
            total=card_voices_count,
            desc="Card voices total",
            position=0,
            leave=True,
            unit="file",
            dynamic_ncols=True
        ) as overall_bar:
            for card in character_cards:
                if remaining_target <= 0:
                    break
                asset_bundle_name = card['assetbundleName']
                self._progress_log(f"Card {card['prefix']}, assetBundleName: {asset_bundle_name}")
                scenario_ids = self._scenario_ids_by_assetbundle.get(asset_bundle_name, [])

                for scenario_id in scenario_ids:
                    if remaining_target <= 0:
                        break
                    self._progress_log(f"Scenario id: {scenario_id}")
                    asset = self._get(
                        "https://storage.sekai.best/sekai-jp-assets/character/member/"
                        f"{asset_bundle_name}/{scenario_id}.asset"
                    ).json()

                    index_return = self._parse_and_download_asset(
                        asset,
                        scenario_id,
                        save_path,
                        select_character_2d_ids,
                        "https://storage.sekai.best/sekai-jp-assets/sound/card_scenario/voice",
                        4,
                        "C",
                        index,
                        remaining_target,
                        overall_bar=overall_bar
                    )

                    if index_return == -1:
                        logger.warning("Get status code 404, perhaps the resource is not exist.")
                        return

                    processed = index_return - index
                    remaining_target -= processed
                    index = index_return

                    if remaining_target <= 0:
                        overall_bar.n = overall_bar.total
                        overall_bar.refresh()
                        logger.success(f"Done with max_count: {card_voices_count}")
                        return

    def download_all(self, character_id: int, card_voices_count: int) -> None:
        self.download_solo_songs(character_id)
        self.download_character_profile_voices(character_id)
        self.download_character_cards_voices(character_id, card_voices_count)

    def download_pure_voices(self, character_id: int, card_voices_count: int) -> None:
        self.download_character_profile_voices(character_id)
        self.download_character_cards_voices(character_id, card_voices_count)

    def _ask_save_texts(self) -> None:
        self._save_texts = questionary.confirm("Save texts into files?", default=True).ask()

    def _download_voice_with_manifest(self, url: str, file_path: str, cleaned_body: str, save_path: str) -> bool:
        success = self._fetch_and_save(url, file_path)
        if success:
            self._write_manifest_line(save_path, file_path, cleaned_body)
        return success

    def start(self) -> None:
        mode = questionary.select(
            "Please select the mode: ",
            choices=[
                questionary.Choice("Download all voices (contains solo songs)", 0),
                questionary.Choice("Download all pure voices", 1),
                questionary.Choice("Download only solo songs", 2),
                questionary.Choice("Download only profile voices", 3),
                questionary.Choice("Download only card voices", 4),
            ]
        ).ask()

        character_id = self.select_character()

        match mode:
            case 0:
                card_voices_count = int(
                    questionary.text("Please input the card max voices count: ", default="800").ask()
                )
                self._ask_save_texts()
                self.download_all(character_id, card_voices_count)

            case 1:
                card_voices_count = int(
                    questionary.text("Please input the card max voices count: ", default="800").ask()
                )
                self._ask_save_texts()
                self.download_pure_voices(character_id, card_voices_count)

            case 2:
                self.download_solo_songs(character_id)

            case 3:
                self._ask_save_texts()
                self.download_character_profile_voices(character_id)

            case 4:
                card_voices_count = int(
                    questionary.text("Please input the card max voices count: ", default="800").ask()
                )
                self._ask_save_texts()
                self.download_character_cards_voices(character_id, card_voices_count)

        if self._manifest_file_instance:
            self._manifest_file_instance.close()
            self._manifest_file_instance = None
            logger.info("Task finished.")
